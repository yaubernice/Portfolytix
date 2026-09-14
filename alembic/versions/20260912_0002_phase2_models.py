"""Phase 2 domain tables: users, portfolios, securities, prices, transactions.

Revision ID: 0002_phase2_models
Revises: 0001_baseline
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_models"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "securities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_securities"),
        sa.UniqueConstraint("ticker", name="uq_securities_ticker"),
    )
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name="fk_portfolios_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_portfolios"),
    )
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"], unique=False)
    op.create_table(
        "prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=False),
        sa.Column("high", sa.Numeric(18, 6), nullable=False),
        sa.Column("low", sa.Numeric(18, 6), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("high >= low", name="ck_prices_high_gte_low"),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0"
            " AND close > 0 AND adjusted_close > 0",
            name="ck_prices_positive",
        ),
        sa.CheckConstraint("volume >= 0", name="ck_prices_volume_nonnegative"),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_prices_security_id_securities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prices"),
        sa.UniqueConstraint(
            "security_id",
            "timestamp",
            name="uq_prices_security_id_timestamp",
        ),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_type", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "transaction_type IN ('BUY', 'SELL')",
            name="ck_transactions_type",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_transactions_quantity_positive"),
        sa.CheckConstraint("price > 0", name="ck_transactions_price_positive"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name="fk_transactions_portfolio_id_portfolios",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_transactions_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transactions"),
    )
    op.create_index(
        "ix_transactions_portfolio_id_security_id",
        "transactions",
        ["portfolio_id", "security_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_portfolio_id_timestamp",
        "transactions",
        ["portfolio_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_portfolio_id_timestamp", table_name="transactions")
    op.drop_index(
        "ix_transactions_portfolio_id_security_id",
        table_name="transactions",
    )
    op.drop_table("transactions")
    op.drop_table("prices")
    op.drop_index("ix_portfolios_user_id", table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_table("securities")
    op.drop_table("users")
