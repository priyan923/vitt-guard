from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.auth import require_api_auth
from app.db.session import get_db
from app.models.payment import Payment
from app.schemas.payment import (
    ApiErrorResponse,
    CreatePaymentRequest,
    MetricsSummaryResponse,
    PaymentListResponse,
    PaymentResponse,
    RequestLogListResponse,
    RequestLogResponse,
)
from app.services.payments import (
    DEFAULT_IDEMPOTENCY_SCOPE,
    PaymentRequestError,
    create_payment,
    get_metrics_summary,
    get_payment,
    get_request_log,
    list_payments,
    list_request_logs,
)

router = APIRouter(dependencies=[Depends(require_api_auth)])
DbSession = Annotated[Session, Depends(get_db)]
MAX_PAGINATION_OFFSET = 1_000_000
ErrorResponses = {
    404: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    503: {"model": ApiErrorResponse},
}


@router.post(
    "/api/v1/payments",
    response_model=PaymentResponse,
    status_code=201,
    responses={
        200: {"model": PaymentResponse, "description": "Idempotent request replayed."},
        409: {"model": ApiErrorResponse, "description": "Idempotency key conflict."},
        500: {"model": ApiErrorResponse, "description": "An unexpected service error occurred."},
        422: {"model": ApiErrorResponse, "description": "Request validation failed."},
        503: {"model": ApiErrorResponse, "description": "A retryable service failure occurred."},
        413: {
            "model": ApiErrorResponse,
            "description": "Request body exceeds the configured limit.",
        },
    },
    tags=["payments"],
    summary="Create a simulated payment",
    description=(
        "Persists a simulated payment only. This endpoint does not authorize, "
        "transfer, or otherwise move money. The idempotency payload is the validated "
        "amount_minor and currency pair; Idempotency-Scope defaults to 'default'."
    ),
)
def create_payment_endpoint(
    payload: CreatePaymentRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            min_length=1,
            max_length=255,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,254}$",
            alias="Idempotency-Key",
        ),
    ],
    session: DbSession,
    idempotency_scope: Annotated[
        str,
        Header(
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
            alias="Idempotency-Scope",
        ),
    ] = DEFAULT_IDEMPOTENCY_SCOPE,
) -> PaymentResponse:
    try:
        result = create_payment(
            session,
            amount_minor=payload.amount_minor,
            currency=payload.currency.value,
            idempotency_key=idempotency_key,
            scope=idempotency_scope,
        )
    except PaymentRequestError as error:
        request.state.internal_payment_id = error.internal_payment_id
        request.state.idempotency_outcome = {
            "idempotency_key_reused": "payload_mismatch",
            "request_in_progress": "in_progress",
        }.get(error.code, "not_used")
        raise error

    request.state.idempotency_outcome = result.idempotency_outcome
    request.state.internal_payment_id = result.internal_payment_id
    response.status_code = result.status_code
    return result.response


@router.get(
    "/api/v1/payments",
    response_model=PaymentListResponse,
    responses={
        422: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    tags=["payments"],
    summary="List payments",
)
def list_payments_endpoint(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_PAGINATION_OFFSET)] = 0,
) -> PaymentListResponse:
    return list_payments(session, limit=limit, offset=offset)


@router.get(
    "/api/v1/payments/{payment_id}",
    response_model=PaymentResponse,
    responses=ErrorResponses,
    tags=["payments"],
    summary="Get a payment",
)
def get_payment_endpoint(
    payment_id: str, request: Request, session: DbSession
) -> PaymentResponse:
    payment: Payment | None = get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "payment_not_found", "message": "Payment was not found."},
        )
    request.state.internal_payment_id = payment.id
    return PaymentResponse.model_validate(payment)


@router.get(
    "/api/v1/requests",
    response_model=RequestLogListResponse,
    responses={
        422: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    tags=["requests"],
    summary="List logged payment request attempts",
)
def list_requests_endpoint(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_PAGINATION_OFFSET)] = 0,
) -> RequestLogListResponse:
    return list_request_logs(session, limit=limit, offset=offset)


@router.get(
    "/api/v1/requests/{request_id}",
    response_model=RequestLogResponse,
    responses=ErrorResponses,
    tags=["requests"],
    summary="Get a logged payment request attempt",
)
def get_request_endpoint(request_id: UUID, session: DbSession) -> RequestLogResponse:
    result = get_request_log(session, request_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "request_not_found", "message": "Request was not found."},
        )
    row, payment_public_id = result
    return RequestLogResponse.model_validate(
        {
            **{
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
            },
            "payment_public_id": payment_public_id,
        }
    )


@router.get(
    "/api/v1/metrics/summary",
    response_model=MetricsSummaryResponse,
    responses={500: {"model": ApiErrorResponse}, 503: {"model": ApiErrorResponse}},
    tags=["metrics"],
    summary="Get persisted payment and request totals",
    description=(
        "Without bounds, returns lifetime totals. Optional timezone-aware bounds use "
        "a UTC [period_start, period_end) interval."
    ),
)
def metrics_summary_endpoint(
    session: DbSession,
    period_start: Annotated[
        AwareDatetime | None,
        Query(alias="start", description="Inclusive UTC period start."),
    ] = None,
    period_end: Annotated[
        AwareDatetime | None,
        Query(alias="end", description="Exclusive UTC period end."),
    ] = None,
) -> MetricsSummaryResponse:
    if period_start is not None and period_end is not None and period_start >= period_end:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_metrics_period",
                "message": "The end of the metrics period must be after its start.",
            },
        )
    return get_metrics_summary(
        session,
        period_start=period_start,
        period_end=period_end,
    )
