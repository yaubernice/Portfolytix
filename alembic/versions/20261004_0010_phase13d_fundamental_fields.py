"""Fundamental fields Alpha Vantage OVERVIEW actually returns.

Revision ID: 0010_phase13d_fundamental_fields
Revises: 0009_phase13c_price_freshness
Create Date: 2026-10-04

Debt/equity is not in OVERVIEW, so it is not added.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_phase13d_fundamental_fields"
down_revision: str | Sequence[str] | None = "0009_phase13c_price_freshness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RATIO = sa.Numeric(18, 8)
_MONEY = sa.Numeric(20, 2)


def upgrade() -> None:
    op.add_column("fundamentals", sa.Column("ebitda", _MONEY, nullable=True))
    op.add_column(
        "fundamentals",
        sa.Column("shares_outstanding", _MONEY, nullable=True),
    )
    op.add_column("fundamentals", sa.Column("price_to_book", _RATIO, nullable=True))
    op.add_column("fundamentals", sa.Column("price_to_sales", _RATIO, nullable=True))
    op.add_column("fundamentals", sa.Column("roa", _RATIO, nullable=True))
    op.add_column(
        "fundamentals",
        sa.Column("earnings_growth", _RATIO, nullable=True),
    )
    op.add_column(
        "fundamentals",
        sa.Column("provider", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fundamentals", "provider")
    op.drop_column("fundamentals", "earnings_growth")
    op.drop_column("fundamentals", "roa")
    op.drop_column("fundamentals", "price_to_sales")
    op.drop_column("fundamentals", "price_to_book")
    op.drop_column("fundamentals", "shares_outstanding")
    op.drop_column("fundamentals", "ebitda")
