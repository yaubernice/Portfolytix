from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobTrigger(StrEnum):
    SCHEDULER = "scheduler"
    CLI = "cli"


class JobRun(Base):
    """One execution of a background job (currently ``update_market_data``).

    Index ``ix_job_runs_job_name_started_at``
        Query: ``SELECT * FROM job_runs WHERE job_name = ?
        ORDER BY started_at DESC LIMIT n``. Ops list / latest status.
        ``job_name`` first (equality), ``started_at`` second (order).
        Tradeoff: a write on every job start.

    Unique partial index ``uq_job_runs_running_job_name``
        At most one ``status = 'running'`` row per ``job_name``.
        This is the database mutex so two API processes cannot ingest
        the same window at once. The application also checks for a
        live running row and records ``skipped``; the unique index is
        the race fallback (IntegrityError → skip).
        Tradeoff: a crashed process leaves ``running`` until the stale
        timeout marks it ``failed``.
    """

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_job_name_started_at", "job_name", "started_at"),
        Index(
            "uq_job_runs_running_job_name",
            "job_name",
            unique=True,
            sqlite_where=text("status = 'running'"),
            postgresql_where=text("status = 'running'"),
        ),
        CheckConstraint(
            "status IN ('running', 'success', 'failed', 'skipped')",
            name="status",
        ),
        CheckConstraint(
            "trigger IN ('scheduler', 'cli')",
            name="trigger",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    window_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_tickers: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    # How many symbols the selection matched, and how many the cap left out.
    symbols_requested: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    symbols_omitted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
