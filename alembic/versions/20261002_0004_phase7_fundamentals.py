"""Phase 7 fundamentals snapshots for structured screening.

Revision ID: 0004_phase7_fundamentals
Revises: 0003_phase6_job_runs
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase7_fundamentals"
down_revision: Union[str, Sequence[str], None] = "0003_phase6_job_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fundamentals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("roe", sa.Numeric(18, 8), nullable=False),
        sa.Column("pe_ratio", sa.Numeric(18, 8), nullable=False),
        sa.Column("revenue_growth", sa.Numeric(18, 8), nullable=False),
        sa.Column("market_cap", sa.Numeric(20, 2), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_fundamentals_security_id_securities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fundamentals"),
        sa.UniqueConstraint("security_id", name="uq_fundamentals_security_id"),
        sa.CheckConstraint(
            "market_cap > 0",
            name="ck_fundamentals_market_cap_positive",
        ),
    )


def downgrade() -> None:
    op.drop_table("fundamentals")
