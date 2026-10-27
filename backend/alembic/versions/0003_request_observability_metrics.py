"""Add normalized request outcomes for observability.

Revision ID: 0003_request_metrics
Revises: 0002_idempotency_key_formats
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_request_metrics"
down_revision: str | Sequence[str] | None = "0002_idempotency_key_formats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "request_logs",
        sa.Column("outcome", sa.String(length=32), server_default="success", nullable=False),
    )
    op.create_check_constraint(
        "ck_request_logs_outcome",
        "request_logs",
        "outcome IN ('success', 'payment_created', 'idempotency_replay', "
        "'payload_conflict', 'validation_error', 'handled_error', 'database_error')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_request_logs_outcome", "request_logs", type_="check")
    op.drop_column("request_logs", "outcome")
