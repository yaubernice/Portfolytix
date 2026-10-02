"""Phase 6 job_runs table for scheduled ingest status.

Revision ID: 0003_phase6_job_runs
Revises: 0002_phase2_models
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase6_job_runs"
down_revision: Union[str, Sequence[str], None] = "0002_phase2_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("accepted", sa.Integer(), nullable=False),
        sa.Column("upserted", sa.Integer(), nullable=False),
        sa.Column("skipped_invalid", sa.Integer(), nullable=False),
        sa.Column("failed_tickers", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_job_runs"),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed', 'skipped')",
            name="ck_job_runs_status",
        ),
        sa.CheckConstraint(
            "trigger IN ('scheduler', 'cli')",
            name="ck_job_runs_trigger",
        ),
    )
    op.create_index(
        "ix_job_runs_job_name_started_at",
        "job_runs",
        ["job_name", "started_at"],
    )
    op.create_index(
        "uq_job_runs_running_job_name",
        "job_runs",
        ["job_name"],
        unique=True,
        sqlite_where=sa.text("status = 'running'"),
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_job_runs_running_job_name", table_name="job_runs")
    op.drop_index("ix_job_runs_job_name_started_at", table_name="job_runs")
    op.drop_table("job_runs")
