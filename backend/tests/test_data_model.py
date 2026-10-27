import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint

from app.models import IdempotencyRecord, Payment, RequestLog
from app.models.payment import generate_public_payment_id
from app.schemas.payment import CreatePaymentRequest, PaymentResponse


@pytest.mark.parametrize("amount_minor", [1, 100_000_000])
def test_create_payment_accepts_amount_boundaries(amount_minor: int) -> None:
    request = CreatePaymentRequest(amount_minor=amount_minor, currency="USD")

    assert request.amount_minor == amount_minor


@pytest.mark.parametrize("amount_minor", [0, -1, 100_000_001, 1.5])
def test_create_payment_rejects_invalid_amounts(amount_minor: int | float) -> None:
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount_minor=amount_minor, currency="USD")


def test_create_payment_rejects_unsupported_currency_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount_minor=2500, currency="CAD")

    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount_minor=2500, currency="USD", card_number="4111111111111111")


def test_public_payment_ids_are_securely_shaped_and_unique() -> None:
    first = generate_public_payment_id()
    second = generate_public_payment_id()

    assert re.fullmatch(r"pay_[A-Za-z0-9_-]{32}", first)
    assert first != second


def test_payment_response_uses_public_id_not_internal_primary_key() -> None:
    assert "payment_id" in PaymentResponse.model_fields
    assert PaymentResponse.model_fields["payment_id"].validation_alias == "public_id"
    assert PaymentResponse.model_fields["payment_id"].serialization_alias is None
    with pytest.raises(ValidationError):
        PaymentResponse(
            public_id="pay_0123456789abcdef0123456789abcdef",
            amount_minor=100,
            currency="USD",
            status="pending",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_schema_has_database_constraints_and_timezone_aware_timestamps() -> None:
    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_payments_amount_minor_range"
        for constraint in Payment.__table__.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"scope", "idempotency_key"}
        for constraint in IdempotencyRecord.__table__.constraints
    )
    assert any(
        isinstance(constraint, CheckConstraint) and constraint.name == "ck_request_logs_status_code"
        for constraint in RequestLog.__table__.constraints
    )
    assert (
        IdempotencyRecord.__table__.c.payment_id.foreign_keys
        and next(iter(IdempotencyRecord.__table__.c.payment_id.foreign_keys)).target_fullname
        == "payments.id"
    )
    assert (
        RequestLog.__table__.c.payment_id.foreign_keys
        and next(iter(RequestLog.__table__.c.payment_id.foreign_keys)).target_fullname
        == "payments.id"
    )
    for model, columns in (
        (Payment, ("created_at", "updated_at")),
        (IdempotencyRecord, ("created_at",)),
        (RequestLog, ("request_at",)),
    ):
        for column_name in columns:
            column_type = model.__table__.columns[column_name].type
            assert isinstance(column_type, DateTime)
            assert column_type.timezone
