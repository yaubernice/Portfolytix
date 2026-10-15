"""Security identity is provider + provider symbol. Ticker is not unique.

Revision ID: 0007_phase13a_security_universe
Revises: 0006_phase13_fundamental_fields
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase13a_security_universe"
down_revision: str | Sequence[str] | None = "0006_phase13_fundamental_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("securities", sa.Column("mic", sa.String(length=8), nullable=True))
    op.add_column(
        "securities",
        sa.Column("industry", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "securities",
        sa.Column("country", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "securities",
        sa.Column(
            "asset_type",
            sa.String(length=16),
            nullable=False,
            server_default="equity",
        ),
    )
    op.add_column(
        "securities",
        sa.Column("provider", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "securities",
        sa.Column("provider_symbol", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "securities",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute(
        "UPDATE securities SET provider = 'seed', provider_symbol = ticker "
        "WHERE provider IS NULL OR provider_symbol IS NULL"
    )
    op.alter_column("securities", "provider", nullable=False)
    op.alter_column("securities", "provider_symbol", nullable=False)
    op.drop_constraint("uq_securities_ticker", "securities", type_="unique")
    op.create_index("ix_securities_ticker", "securities", ["ticker"])
    op.create_unique_constraint(
        "uq_securities_provider_symbol",
        "securities",
        ["provider", "provider_symbol"],
    )
    op.create_check_constraint(
        "ck_securities_asset_type",
        "securities",
        "asset_type IN ('equity', 'etf', 'fund', 'index', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_securities_asset_type", "securities", type_="check")
    op.drop_constraint(
        "uq_securities_provider_symbol",
        "securities",
        type_="unique",
    )
    op.drop_index("ix_securities_ticker", table_name="securities")
    op.create_unique_constraint("uq_securities_ticker", "securities", ["ticker"])
    op.drop_column("securities", "is_active")
    op.drop_column("securities", "provider_symbol")
    op.drop_column("securities", "provider")
    op.drop_column("securities", "asset_type")
    op.drop_column("securities", "country")
    op.drop_column("securities", "industry")
    op.drop_column("securities", "mic")
