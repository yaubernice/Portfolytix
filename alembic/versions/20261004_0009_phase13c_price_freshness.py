"""Price source, ingest time, and job selection counts.

Revision ID: 0009_phase13c_price_freshness
Revises: 0008_phase13b_watchlists
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_phase13c_price_freshness"
down_revision: str | Sequence[str] | None = "0008_phase13b_watchlists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prices", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column(
        "prices",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_runs",
        sa.Column(
            "symbols_requested",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "job_runs",
        sa.Column(
            "symbols_omitted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "symbols_omitted")
    op.drop_column("job_runs", "symbols_requested")
    op.drop_column("prices", "ingested_at")
    op.drop_column("prices", "source")
