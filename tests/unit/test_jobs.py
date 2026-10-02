from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JobRun, JobStatus, Price, Security
from app.jobs.market_data_job import (
    JOB_NAME,
    default_ingest_window,
    update_market_data,
)
from app.jobs.scheduler import start_scheduler
from app.market_data.errors import ProviderError
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(
        self,
        bars: dict[str, list[RawBar]],
        errors: dict[str, str] | None = None,
    ) -> None:
        self.bars = bars
        self.errors = errors or {}
        self.calls: list[tuple[str, date, date]] = []

    def fetch_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> list[RawBar]:
        self.calls.append((ticker, start, end))
        if ticker in self.errors:
            raise ProviderError(self.errors[ticker])
        return [
            bar
            for bar in self.bars.get(ticker, [])
            if start <= bar.day <= end
        ]


def _bar(ticker: str, day: date, close: str) -> RawBar:
    close_d = Decimal(close)
    return RawBar(
        ticker=ticker,
        day=day,
        open=close_d,
        high=close_d + Decimal("1"),
        low=close_d - Decimal("1") if close_d > 1 else close_d,
        close=close_d,
        adjusted_close=close_d,
        volume=10,
    )


def _apple(session: Session) -> Security:
    row = Security(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    session.add(row)
    session.flush()
    return row


def test_default_ingest_window() -> None:
    start, end = default_ingest_window(date(2024, 1, 10), 7)
    assert start == date(2024, 1, 3)
    assert end == date(2024, 1, 10)


def test_start_scheduler_respects_enabled_flag() -> None:
    assert start_scheduler(enabled=False) is None
    scheduler = start_scheduler(
        enabled=True,
        cron="0 22 * * *",
        job_func=lambda: None,
        start_date=datetime(2099, 1, 1, tzinfo=UTC),
    )
    assert scheduler is not None
    job = scheduler.get_job("update_market_data")
    assert job is not None
    scheduler.shutdown(wait=False)


def test_update_market_data_records_success(sqlite_session: Session) -> None:
    _apple(sqlite_session)
    day = date(2024, 1, 2)
    provider = FakeProvider({"AAPL": [_bar("AAPL", day, "100")]})
    run = update_market_data(
        sqlite_session,
        tickers=["AAPL"],
        start=day,
        end=day,
        provider=provider,
        trigger="cli",
    )
    sqlite_session.flush()
    assert run.job_name == JOB_NAME
    assert run.status == JobStatus.SUCCESS
    assert run.trigger == "cli"
    assert run.fetched == 1
    assert run.accepted == 1
    assert run.failed_tickers == []
    assert sqlite_session.scalar(select(Price.close)) == Decimal("100")


def test_update_skips_when_already_running(sqlite_session: Session) -> None:
    _apple(sqlite_session)
    live = JobRun(
        job_name=JOB_NAME,
        status=JobStatus.RUNNING,
        trigger="scheduler",
        started_at=datetime.now(UTC),
        failed_tickers=[],
    )
    sqlite_session.add(live)
    sqlite_session.flush()
    provider = FakeProvider({"AAPL": [_bar("AAPL", date(2024, 1, 2), "100")]})
    run = update_market_data(
        sqlite_session,
        tickers=["AAPL"],
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
        provider=provider,
        trigger="cli",
    )
    assert run.status == JobStatus.SKIPPED
    assert run.error is not None and run.error.startswith("already_running")
    assert provider.calls == []
    assert sqlite_session.scalars(select(Price)).all() == []


def test_stale_running_is_expired_then_job_runs(sqlite_session: Session) -> None:
    _apple(sqlite_session)
    stale = JobRun(
        job_name=JOB_NAME,
        status=JobStatus.RUNNING,
        trigger="scheduler",
        started_at=datetime.now(UTC) - timedelta(hours=3),
        failed_tickers=[],
    )
    sqlite_session.add(stale)
    sqlite_session.flush()
    day = date(2024, 1, 2)
    provider = FakeProvider({"AAPL": [_bar("AAPL", day, "100")]})
    run = update_market_data(
        sqlite_session,
        tickers=["AAPL"],
        start=day,
        end=day,
        provider=provider,
        trigger="cli",
    )
    sqlite_session.flush()
    sqlite_session.refresh(stale)
    assert stale.status == JobStatus.FAILED
    assert stale.error == "stale_running"
    assert run.status == JobStatus.SUCCESS
    assert len(provider.calls) == 1


def test_ticker_failure_marks_job_failed(sqlite_session: Session) -> None:
    _apple(sqlite_session)
    day = date(2024, 1, 2)
    provider = FakeProvider({}, errors={"AAPL": "vendor down"})
    run = update_market_data(
        sqlite_session,
        tickers=["AAPL"],
        start=day,
        end=day,
        provider=provider,
        trigger="cli",
    )
    assert run.status == JobStatus.FAILED
    assert run.failed_tickers == ["AAPL"]
    assert sqlite_session.scalars(select(Price)).all() == []
