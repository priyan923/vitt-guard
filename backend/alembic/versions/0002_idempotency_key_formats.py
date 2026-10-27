"""Constrain idempotency scope and key formats.

Revision ID: 0002_idempotency_key_formats
Revises: 0001_stage2
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_idempotency_key_formats"
down_revision: str | Sequence[str] | None = "0001_stage2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_idempotency_scope_format",
        "idempotency_records",
        "scope ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'",
    )
    op.create_check_constraint(
        "ck_idempotency_key_format",
        "idempotency_records",
        "idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._~-]{0,254}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_idempotency_key_format",
        "idempotency_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_idempotency_scope_format",
        "idempotency_records",
        type_="check",
    )
