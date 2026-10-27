"""Create payment, idempotency, and request log tables.

Revision ID: 0001_stage2
Revises:
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_stage2"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_minor >= 1 AND amount_minor <= 100000000",
            name="ck_payments_amount_minor_range",
        ),
        sa.CheckConstraint(
            "currency IN ('USD', 'EUR', 'GBP')",
            name="ck_payments_currency_supported",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="ck_payments_status_supported",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("public_id", name="uq_payments_public_id"),
    )
    op.create_index("ix_payments_created_at", "payments", ["created_at"], unique=False)

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("response_status_code", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(scope)) > 0", name="ck_idempotency_scope_not_empty"),
        sa.CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_idempotency_key_not_empty",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_idempotency_request_hash_sha256",
        ),
        sa.CheckConstraint(
            "(response_status_code IS NULL AND response_body IS NULL) OR "
            "(response_status_code BETWEEN 100 AND 599 AND response_body IS NOT NULL)",
            name="ck_idempotency_response_pair",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_idempotency_records_payment_id_payments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
        sa.UniqueConstraint(
            "scope",
            "idempotency_key",
            name="uq_idempotency_scope_key",
        ),
    )
    op.create_index(
        "ix_idempotency_payment_id",
        "idempotency_records",
        ["payment_id"],
        unique=False,
    )

    op.create_table(
        "request_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_method", sa.String(length=10), nullable=False),
        sa.Column("api_path", sa.String(length=2048), nullable=False),
        sa.Column(
            "request_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("http_status_code", sa.SmallInteger(), nullable=False),
        sa.Column("processing_duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "idempotency_outcome",
            sa.String(length=24),
            server_default="not_used",
            nullable=False,
        ),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("sanitized_error_code", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "length(request_method) BETWEEN 1 AND 10 AND request_method = upper(request_method)",
            name="ck_request_logs_method",
        ),
        sa.CheckConstraint(
            "length(api_path) BETWEEN 1 AND 2048 AND api_path LIKE '/%'",
            name="ck_request_logs_api_path",
        ),
        sa.CheckConstraint(
            "http_status_code BETWEEN 100 AND 599",
            name="ck_request_logs_status_code",
        ),
        sa.CheckConstraint(
            "processing_duration_ms >= 0",
            name="ck_request_logs_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "idempotency_outcome IN "
            "('not_used', 'created', 'replayed', 'payload_mismatch', 'in_progress')",
            name="ck_request_logs_idempotency_outcome",
        ),
        sa.CheckConstraint(
            "sanitized_error_code IS NULL OR length(sanitized_error_code) BETWEEN 1 AND 100",
            name="ck_request_logs_error_code_length",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_request_logs_payment_id_payments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_request_logs"),
        sa.UniqueConstraint("request_id", name="uq_request_logs_request_id"),
    )
    op.create_index("ix_request_logs_request_at", "request_logs", ["request_at"], unique=False)
    op.create_index("ix_request_logs_payment_id", "request_logs", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_request_logs_payment_id", table_name="request_logs")
    op.drop_index("ix_request_logs_request_at", table_name="request_logs")
    op.drop_table("request_logs")
    op.drop_index("ix_idempotency_payment_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_table("payments")
