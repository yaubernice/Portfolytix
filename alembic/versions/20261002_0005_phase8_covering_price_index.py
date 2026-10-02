"""Phase 8 covering index for analytics price-history reads.

Revision ID: 0005_phase8_covering_price_index
Revises: 0004_phase7_fundamentals
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_phase8_covering_price_index"
down_revision: Union[str, Sequence[str], None] = "0004_phase7_fundamentals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_prices_security_id_timestamp"


def upgrade() -> None:
    # Keep the same business key and name, but include the only value read by
    # portfolio analytics. PostgreSQL can then satisfy the projected history
    # query from the btree without visiting every matching heap row.
    op.drop_constraint(INDEX_NAME, "prices", type_="unique") #remove old unique constraint
    op.create_index(
        INDEX_NAME,
        "prices",
        ["security_id", "timestamp"],
        unique=True,
        postgresql_include=["adjusted_close"], #security and timestamp are the columns that are used to uniquely identify a row, and adjusted_close is the only value that is read by the projected analytics query
    )


def downgrade() -> None: 
    op.drop_index(INDEX_NAME, table_name="prices")
    op.create_unique_constraint(
        INDEX_NAME,
        "prices",
        ["security_id", "timestamp"],
    )
