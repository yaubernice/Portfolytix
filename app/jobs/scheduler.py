"""In-process APScheduler. One process, one replica — not a task queue."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.cache import commit_and_invalidate, get_cache
from app.core.config import settings
from app.db.session import SessionLocal
from app.jobs.market_data_job import update_market_data

logger = logging.getLogger(__name__)


def run_scheduled_update_market_data() -> None:
    """Open a session, ingest, commit. Runs on a thread, not the event loop."""
    session = SessionLocal()
    try:
        update_market_data(session, trigger="scheduler")
        commit_and_invalidate(session, get_cache())
    except Exception:
        session.rollback()
        logger.exception("scheduled_update_market_data_failed")
    finally:
        session.close()


# create the scheduler, register the market-data job, start it
def start_scheduler(
    *,
    enabled: bool | None = None,  # when scheduling actually starts
    cron: str | None = None,  # override the configured cron expression
    job_func: Callable[[], None] | None = None,  # function the cron calls
    start_date: datetime | None = None,
) -> BackgroundScheduler | None:
    """Start the background scheduler if ``SCHEDULER_ENABLED`` is true.

    Jobs run in a thread pool so FastAPI request handlers are not blocked.
    Tests pass ``enabled=False`` (default via env) so TestClient never
    downloads vendor data.
    """
    on = settings.scheduler_enabled if enabled is None else enabled
    if not on:
        logger.info("scheduler_disabled")
        return None

    expression = cron or settings.market_data_cron
    fields = expression.split() #split the cron expression into 5 fields
    if len(fields) != 5:
        raise ValueError(
            f"MARKET_DATA_CRON must have 5 fields (m h dom mon dow); got {expression!r}"
        )
    trigger = CronTrigger(
        minute=fields[0],
        hour=fields[1],
        day=fields[2],
        month=fields[3],
        day_of_week=fields[4],
        timezone=UTC,
    )
    scheduler = BackgroundScheduler(timezone=UTC) #create a new scheduler
    job_kwargs: dict[str, object] = {}
    if start_date is not None:
        job_kwargs["next_run_time"] = start_date #set the next run time
    scheduler.add_job(
        job_func or run_scheduled_update_market_data, #run the market-data job
        trigger=trigger,
        id="update_market_data",
        name="update_market_data",
        max_instances=1, #run onlt 1 instance of the job at a time
        coalesce=True, #multiple missed ececutions can be combined into one execution
        replace_existing=True, #replace the existing job with the new one
        # a missed fire can still run if we notice it within 1 hour
        misfire_grace_time=3600,
        **job_kwargs,
    )
    scheduler.start()
    logger.info(
        "scheduler_started",
        extra={"cron": expression, "job": "update_market_data"},
    )
    return scheduler
