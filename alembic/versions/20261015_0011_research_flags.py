"""User flags on a security or a sector.

Revision ID: 0011_research_flags
Revises: 0010_phase13d_fundamental_fields
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_research_flags"
down_revision: str | Sequence[str] | None = "0010_phase13d_fundamental_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_type IN ('security', 'sector')",
            name="ck_research_flags_target_type",
        ),
        sa.CheckConstraint(
            "(target_type = 'security' AND security_id IS NOT NULL "
            "AND sector IS NULL) OR "
            "(target_type = 'sector' AND sector IS NOT NULL "
            "AND security_id IS NULL)",
            name="ck_research_flags_target",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_flags_user_id", "research_flags", ["user_id"])
    op.create_index(
        "uq_research_flags_user_security",
        "research_flags",
        ["user_id", "security_id"],
        unique=True,
        sqlite_where=sa.text("security_id IS NOT NULL"),
        postgresql_where=sa.text("security_id IS NOT NULL"),
    )
    op.create_index(
        "uq_research_flags_user_sector",
        "research_flags",
        ["user_id", "sector"],
        unique=True,
        sqlite_where=sa.text("sector IS NOT NULL"),
        postgresql_where=sa.text("sector IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_research_flags_user_sector", table_name="research_flags")
    op.drop_index("uq_research_flags_user_security", table_name="research_flags")
    op.drop_index("ix_research_flags_user_id", table_name="research_flags")
    op.drop_table("research_flags")
