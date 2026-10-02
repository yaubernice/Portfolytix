"""update_market_data: record status, then reuse the Phase 5 ingest callable."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import queue_version_bump
from app.core.config import settings
from app.db.models import JobRun, JobStatus, JobTrigger
from app.db.seed import SECURITIES
from app.market_data.factory import build_provider
from app.market_data.provider import MarketDataProvider
from app.repositories.job_run_repository import (
    JOB_NAME_MARKET_DATA,
    JobRunRepository,
)
from app.services.market_data_service import IngestReport, MarketDataService

logger = logging.getLogger(__name__)

DEFAULT_TICKERS = [spec.ticker for spec in SECURITIES]
JOB_NAME = JOB_NAME_MARKET_DATA


def default_ingest_window(today: date, lookback_days: int) -> tuple[date, date]:
    # calculates the fetch period
    """Inclusive ``[today - lookback_days, today]``. Overlap is cheap (upsert)."""
    if lookback_days < 1: #if 0, just look at today so violate purpose of lookback
        raise ValueError("lookback_days must be >= 1")
    return today - timedelta(days=lookback_days), today


def run_market_data_ingest(
    session: Session,
    *,
    tickers: list[str] | None = None,
    start: date,
    end: date,
    provider: MarketDataProvider | None = None,
) -> IngestReport:
    # use the given provider, otherwise build one from config
    adapter = provider or build_provider()
    service = MarketDataService(session, adapter) #create a service instance
    return service.ingest(tickers or DEFAULT_TICKERS, start, end) #ingest the data


def update_market_data(
    session: Session,
    *,
    tickers: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    provider: MarketDataProvider | None = None,
    trigger: JobTrigger | str = JobTrigger.SCHEDULER, #records how the job started
) -> JobRun:
    """Run ingest and persist a ``job_runs`` row.

    HTTP handlers never call this. The scheduler and the CLI do. A second
    overlapping run is recorded as ``skipped`` instead of downloading twice.
    """
    jobs = JobRunRepository(session) #manage job_runs table
    trigger_value = str(trigger)
    # fail leftover running rows older than the stale timeout
    stale = timedelta(seconds=settings.job_stale_after_seconds)
    expired = jobs.fail_stale_running(JOB_NAME, stale)
    session.flush() #save the job to the database
    if expired:
        logger.warning(
            "job_stale_expired",
            extra={"job_name": JOB_NAME, "expired": expired},
        )
        # drop cached ORM state so the next load comes from the database
        session.expire_all()

    live = jobs.get_running(JOB_NAME) #check if the job is already running
    if live is not None:
        skipped = _new_run( #create a new job run record for the skipped job
            trigger=trigger_value,
            status=JobStatus.SKIPPED,
            error=f"already_running:{live.id}",
        )
        jobs.add(skipped)
        logger.info(
            "job_skipped",
            extra={"job_name": JOB_NAME, "running_id": str(live.id)},
        )
        return skipped

    window_start, window_end = _resolve_window(start, end) 
    adapter = provider or build_provider()
    run = _new_run(
        trigger=trigger_value,
        status=JobStatus.RUNNING,
        window_start=window_start,
        window_end=window_end,
        provider=adapter.name,
    )
    try:
        jobs.add(run)
        session.flush()
    except IntegrityError: #if the job is already running, skip it
        session.rollback() #rollback to resets the transaction
        raced = _new_run( #create a new job run record for the skipped job
            trigger=trigger_value,
            status=JobStatus.SKIPPED,
            error="already_running",
            window_start=window_start,
            window_end=window_end,
            provider=adapter.name,
        )
        session.add(raced)
        session.flush()
        logger.info("job_skipped", extra={"job_name": JOB_NAME, "reason": "race"})
        return raced

    logger.info(
        "job_started", #start the job
        extra={
            "job_name": JOB_NAME,
            "job_run_id": str(run.id),
            "trigger": trigger_value,
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "provider": adapter.name,
        },
    )
    try:
        report = run_market_data_ingest( #ingest the data
            session,
            tickers=tickers,
            start=window_start,
            end=window_end,
            provider=adapter,
        )
    except Exception as exc: #changes JobRun to failed status
        _finish(
            run,
            status=JobStatus.FAILED,
            error=str(exc),
        )
        logger.exception(
            "job_failed",
            extra={"job_name": JOB_NAME, "job_run_id": str(run.id)},
        )
        return run

    _apply_report(run, report) #updates the JobRun record with the ingest report
    if run.upserted > 0:
        queue_version_bump(session, "prices")
    logger.info(
        "job_finished", #job finished successfully
        extra={
            "job_name": JOB_NAME,
            "job_run_id": str(run.id),
            "status": run.status,
            "fetched": run.fetched,
            "accepted": run.accepted,
            "upserted": run.upserted,
            "failed_tickers": run.failed_tickers,
        },
    )
    return run


def _resolve_window(start: date | None, end: date | None) -> tuple[date, date]:
    # decide the actual inclusive date window
    today = datetime.now(UTC).date()
    window_end = end or today
    # if start is omitted, use the default lookback window
    window_start = start or default_ingest_window(
        window_end,
        settings.market_data_lookback_days,
    )[0]
    if window_start > window_end:
        raise ValueError("ingest start must be on or before end")
    return window_start, window_end


def _new_run( #create a new job run record
    *,
    trigger: str,
    status: JobStatus,
    error: str | None = None,
    window_start: date | None = None,
    window_end: date | None = None,
    provider: str | None = None,
) -> JobRun:
    now = datetime.now(UTC)
    finished = now if status != JobStatus.RUNNING else None
    return JobRun(
        job_name=JOB_NAME,
        status=status,
        trigger=trigger,
        started_at=now,
        finished_at=finished,
        window_start=window_start,
        window_end=window_end,
        provider=provider,
        error=error,
        failed_tickers=[],
    )


def _apply_report(run: JobRun, report: IngestReport) -> None:
    # copy ingest totals onto the JobRun row
    run.fetched = sum(row.fetched for row in report.results)
    run.accepted = sum(row.accepted for row in report.results)
    run.upserted = sum(row.upserted for row in report.results)
    run.skipped_invalid = sum(row.skipped_invalid for row in report.results)
    run.failed_tickers = report.failed_tickers
    run.provider = report.provider
    if report.failed_tickers:
        _finish(
            run,
            status=JobStatus.FAILED,
            error="ticker_failures:" + ",".join(report.failed_tickers),
        )
        return
    _finish(run, status=JobStatus.SUCCESS)


def _finish(run: JobRun, *, status: JobStatus, error: str | None = None) -> None:
    run.status = status
    run.finished_at = datetime.now(UTC)
    if error is not None:
        run.error = error
