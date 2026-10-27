import secrets
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MIN_PAYMENT_AMOUNT = 1
MAX_PAYMENT_AMOUNT = 100_000_000


class PaymentCurrency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IdempotencyOutcome(str, Enum):
    NOT_USED = "not_used"
    CREATED = "created"
    REPLAYED = "replayed"
    PAYLOAD_MISMATCH = "payload_mismatch"
    IN_PROGRESS = "in_progress"


def generate_public_payment_id() -> str:
    return f"pay_{secrets.token_urlsafe(24)}"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            f"amount_minor >= {MIN_PAYMENT_AMOUNT} AND amount_minor <= {MAX_PAYMENT_AMOUNT}",
            name="ck_payments_amount_minor_range",
        ),
        CheckConstraint(
            "currency IN ('USD', 'EUR', 'GBP')",
            name="ck_payments_currency_supported",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="ck_payments_status_supported",
        ),
        Index("ix_payments_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=generate_public_payment_id
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PaymentStatus.PENDING.value,
        server_default=PaymentStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
        CheckConstraint("length(trim(scope)) > 0", name="ck_idempotency_scope_not_empty"),
        CheckConstraint(
            "scope ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'",
            name="ck_idempotency_scope_format",
        ),
        CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_idempotency_key_not_empty",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._~-]{0,254}$'",
            name="ck_idempotency_key_format",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_idempotency_request_hash_sha256",
        ),
        CheckConstraint(
            "(response_status_code IS NULL AND response_body IS NULL) OR "
            "(response_status_code BETWEEN 100 AND 599 AND response_body IS NOT NULL)",
            name="ck_idempotency_response_pair",
        ),
        Index("ix_idempotency_payment_id", "payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    response_status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RequestLog(Base):
    __tablename__ = "request_logs"
    __table_args__ = (
        CheckConstraint(
            "length(request_method) BETWEEN 1 AND 10 AND request_method = upper(request_method)",
            name="ck_request_logs_method",
        ),
        CheckConstraint(
            "length(api_path) BETWEEN 1 AND 2048 AND api_path LIKE '/%'",
            name="ck_request_logs_api_path",
        ),
        CheckConstraint(
            "http_status_code BETWEEN 100 AND 599",
            name="ck_request_logs_status_code",
        ),
        CheckConstraint("processing_duration_ms >= 0", name="ck_request_logs_duration_nonnegative"),
        CheckConstraint(
            "idempotency_outcome IN "
            "('not_used', 'created', 'replayed', 'payload_mismatch', 'in_progress')",
            name="ck_request_logs_idempotency_outcome",
        ),
        CheckConstraint(
            "outcome IN ('success', 'payment_created', 'idempotency_replay', "
            "'payload_conflict', 'validation_error', 'handled_error', 'database_error')",
            name="ck_request_logs_outcome",
        ),
        CheckConstraint(
            "sanitized_error_code IS NULL OR length(sanitized_error_code) BETWEEN 1 AND 100",
            name="ck_request_logs_error_code_length",
        ),
        Index("ix_request_logs_request_at", "request_at"),
        Index("ix_request_logs_payment_id", "payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    request_method: Mapped[str] = mapped_column(String(10), nullable=False)
    api_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    request_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    http_status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    processing_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_outcome: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=IdempotencyOutcome.NOT_USED.value
    )
    outcome: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="success"
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sanitized_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
