from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models.payment import (
    MAX_PAYMENT_AMOUNT,
    MIN_PAYMENT_AMOUNT,
    PaymentCurrency,
    PaymentStatus,
)


class CreatePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(
        strict=True,
        ge=MIN_PAYMENT_AMOUNT,
        le=MAX_PAYMENT_AMOUNT,
        description="Amount in the currency's smallest unit (for example, cents).",
    )
    currency: PaymentCurrency


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str = Field(
        validation_alias="public_id",
        pattern=r"^pay_[A-Za-z0-9_-]{32}$",
    )
    amount_minor: int
    currency: PaymentCurrency
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class ApiErrorDetail(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail
    request_id: UUID


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
    limit: int
    offset: int


class RequestLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    request_id: UUID
    request_method: str
    api_path: str
    request_at: datetime
    http_status_code: int
    processing_duration_ms: int
    idempotency_outcome: str
    outcome: str
    payment_id: str | None = Field(
        default=None,
        validation_alias="payment_public_id",
        serialization_alias="payment_id",
    )
    sanitized_error_code: str | None = None

    @field_validator("request_at")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class RequestLogListResponse(BaseModel):
    items: list[RequestLogResponse]
    total: int
    limit: int
    offset: int


class MetricsSummaryResponse(BaseModel):
    period_start: AwareDatetime | None
    period_end: AwareDatetime | None
    total_payments: int
    payments_by_status: dict[PaymentStatus, int]
    total_requests: int
    payment_attempts: int
    successful_requests: int
    conflicts: int
    idempotency_replays: int
