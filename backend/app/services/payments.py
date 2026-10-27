import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.payment import IdempotencyRecord, Payment, PaymentStatus, RequestLog
from app.schemas.payment import (
    MetricsSummaryResponse,
    PaymentListResponse,
    PaymentResponse,
    RequestLogListResponse,
    RequestLogResponse,
)

DEFAULT_IDEMPOTENCY_SCOPE = "default"
MAX_TRANSACTION_ATTEMPTS = 3
RETRYABLE_POSTGRES_STATES = {"40001", "40P01"}


class _RetryTransaction(Exception):
    pass


class PaymentRequestError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        internal_payment_id: UUID | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.internal_payment_id = internal_payment_id
        super().__init__(message)


@dataclass(frozen=True)
class PaymentCreation:
    response: PaymentResponse
    status_code: int
    idempotency_outcome: str
    internal_payment_id: UUID


def canonical_payment_payload(amount_minor: int, currency: str) -> str:
    return json.dumps(
        {"amount_minor": amount_minor, "currency": currency},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def hash_payment_payload(amount_minor: int, currency: str) -> str:
    payload = canonical_payment_payload(amount_minor, currency)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_payment(
    session: Session,
    *,
    amount_minor: int,
    currency: str,
    idempotency_key: str,
    scope: str = DEFAULT_IDEMPOTENCY_SCOPE,
) -> PaymentCreation:
    request_hash = hash_payment_payload(amount_minor, currency)

    for attempt in range(MAX_TRANSACTION_ATTEMPTS):
        try:
            return _create_payment_transaction(
                session,
                amount_minor=amount_minor,
                currency=currency,
                idempotency_key=idempotency_key,
                scope=scope,
                request_hash=request_hash,
            )
        except _RetryTransaction:
            session.rollback()
        except DBAPIError as error:
            session.rollback()
            sqlstate = getattr(error.orig, "sqlstate", None) or getattr(
                error.orig, "pgcode", None
            )
            if sqlstate not in RETRYABLE_POSTGRES_STATES:
                raise

        if attempt == MAX_TRANSACTION_ATTEMPTS - 1:
            raise PaymentRequestError(
                503,
                "idempotency_transaction_retry",
                "The request encountered a concurrent database conflict; retry with the same key.",
            )

    raise RuntimeError("Idempotency transaction retry loop exited unexpectedly.")


def _create_payment_transaction(
    session: Session,
    *,
    amount_minor: int,
    currency: str,
    idempotency_key: str,
    scope: str,
    request_hash: str,
) -> PaymentCreation:
    with session.begin():
        inserted_id = session.scalar(
            insert(IdempotencyRecord)
            .values(
                scope=scope,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            .on_conflict_do_nothing(
                constraint="uq_idempotency_scope_key",
            )
            .returning(IdempotencyRecord.id)
        )

        if inserted_id is None:
            record = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if record is None:
                raise _RetryTransaction
            if record.request_hash != request_hash:
                raise PaymentRequestError(
                    409,
                    "idempotency_key_reused",
                    "This idempotency key was already used with a different request.",
                    internal_payment_id=record.payment_id,
                )
            if record.response_body is None or record.payment_id is None:
                raise PaymentRequestError(
                    409,
                    "request_in_progress",
                    "A request with this idempotency key is still in progress.",
                )

            response_body = dict(record.response_body)
            response_body["public_id"] = response_body["payment_id"]
            return PaymentCreation(
                response=PaymentResponse.model_validate(response_body),
                status_code=200,
                idempotency_outcome="replayed",
                internal_payment_id=record.payment_id,
            )

        payment = Payment(amount_minor=amount_minor, currency=currency)
        session.add(payment)
        session.flush()

        response = PaymentResponse.model_validate(payment)
        record = session.get(IdempotencyRecord, inserted_id)
        if record is None:
            raise RuntimeError("New idempotency record was not persisted.")
        record.payment_id = payment.id
        record.response_status_code = 201
        record.response_body = response.model_dump(mode="json")
        session.flush()

        return PaymentCreation(
            response=response,
            status_code=201,
            idempotency_outcome="created",
            internal_payment_id=payment.id,
        )


def list_payments(session: Session, *, limit: int, offset: int) -> PaymentListResponse:
    total = session.scalar(select(func.count()).select_from(Payment)) or 0
    payments = session.scalars(
        select(Payment)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaymentListResponse(
        items=[PaymentResponse.model_validate(payment) for payment in payments],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_payment(session: Session, public_id: str) -> Payment | None:
    return session.scalar(select(Payment).where(Payment.public_id == public_id))


def list_request_logs(
    session: Session, *, limit: int, offset: int
) -> RequestLogListResponse:
    total = session.scalar(select(func.count()).select_from(RequestLog)) or 0
    rows = session.execute(
        select(RequestLog, Payment.public_id)
        .outerjoin(Payment, RequestLog.payment_id == Payment.id)
        .order_by(RequestLog.request_at.desc(), RequestLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return RequestLogListResponse(
        items=[
            RequestLogResponse.model_validate(
                {
                    **{
                        column.name: getattr(row, column.name)
                        for column in RequestLog.__table__.columns
                    },
                    "payment_public_id": public_id,
                }
            )
            for row, public_id in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_request_log(
    session: Session, request_id: UUID
) -> tuple[RequestLog, str | None] | None:
    return session.execute(
        select(RequestLog, Payment.public_id)
        .outerjoin(Payment, RequestLog.payment_id == Payment.id)
        .where(RequestLog.request_id == request_id)
    ).one_or_none()


def get_metrics_summary(
    session: Session,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> MetricsSummaryResponse:
    if period_start is not None and period_start.utcoffset() is None:
        raise ValueError("period_start must be timezone-aware")
    if period_end is not None and period_end.utcoffset() is None:
        raise ValueError("period_end must be timezone-aware")
    if period_start is not None:
        period_start = period_start.astimezone(UTC)
    if period_end is not None:
        period_end = period_end.astimezone(UTC)

    payment_filters = []
    request_filters = []
    if period_start is not None:
        payment_filters.append(Payment.created_at >= period_start)
        request_filters.append(RequestLog.request_at >= period_start)
    if period_end is not None:
        payment_filters.append(Payment.created_at < period_end)
        request_filters.append(RequestLog.request_at < period_end)

    payments_by_status = {status.value: 0 for status in PaymentStatus}
    payment_counts = session.execute(
        select(Payment.status, func.count())
        .where(*payment_filters)
        .group_by(Payment.status)
    )
    for status, count in payment_counts:
        payments_by_status[status] = count

    total_payments = sum(payments_by_status.values())
    request_metrics = session.execute(
        select(
            func.count(),
            func.count().filter(RequestLog.http_status_code.between(200, 299)),
            func.count().filter(RequestLog.http_status_code == 409),
            func.count().filter(RequestLog.idempotency_outcome == "replayed"),
            func.count().filter(RequestLog.api_path.like("/api/v1/payments%")),
        ).where(*request_filters)
    ).one()
    return MetricsSummaryResponse(
        period_start=period_start,
        period_end=period_end,
        total_payments=total_payments,
        payments_by_status=payments_by_status,
        total_requests=request_metrics[0],
        successful_requests=request_metrics[1],
        conflicts=request_metrics[2],
        idempotency_replays=request_metrics[3],
        payment_attempts=request_metrics[4],
    )
