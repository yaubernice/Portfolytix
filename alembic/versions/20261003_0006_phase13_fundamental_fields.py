"""Optional fundamental fields for earnings, margin, dividend, and beta.

Revision ID: 0006_phase13_fundamental_fields
Revises: 0005_phase8_covering_price_index
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase13_fundamental_fields"
down_revision: str | Sequence[str] | None = "0005_phase8_covering_price_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RATIO = sa.Numeric(18, 8)
_MONEY = sa.Numeric(20, 2)


def upgrade() -> None:
    op.add_column("fundamentals", sa.Column("eps", _RATIO, nullable=True))
    op.add_column("fundamentals", sa.Column("revenue", _MONEY, nullable=True))
    op.add_column("fundamentals", sa.Column("profit_margin", _RATIO, nullable=True))
    op.add_column(
        "fundamentals",
        sa.Column("dividend_yield", _RATIO, nullable=True),
    )
    op.add_column("fundamentals", sa.Column("beta", _RATIO, nullable=True))


def downgrade() -> None:
    op.drop_column("fundamentals", "beta")
    op.drop_column("fundamentals", "dividend_yield")
    op.drop_column("fundamentals", "profit_margin")
    op.drop_column("fundamentals", "revenue")
    op.drop_column("fundamentals", "eps")
