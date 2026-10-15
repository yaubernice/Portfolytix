from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Price, Security
from app.jobs.market_data_job import run_market_data_ingest
from app.market_data.errors import ProviderError
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar
from app.services.market_data_service import MarketDataService


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(
        self,
        bars: dict[str, list[RawBar]],
        errors: dict[str, str] | None = None,
    ) -> None:
        self.bars = bars
        self.errors = errors or {}

    def fetch_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> list[RawBar]:
        if ticker in self.errors:
            raise ProviderError(self.errors[ticker])
        return [
            bar
            for bar in self.bars.get(ticker, [])
            if start <= bar.day <= end
        ]


def _bar(ticker: str, day: date, close: str, high: str | None = None) -> RawBar:
    close_d = Decimal(close)
    high_d = Decimal(high) if high is not None else close_d + Decimal("1")
    return RawBar(
        ticker=ticker,
        day=day,
        open=close_d,
        high=high_d,
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


def test_ingest_is_idempotent_and_updates(
    sqlite_session: Session,
) -> None:
    apple = _apple(sqlite_session)
    day = date(2024, 1, 2)
    provider = FakeProvider({"AAPL": [_bar("AAPL", day, "100")]})
    first = MarketDataService(sqlite_session, provider).ingest(
        ["AAPL"], day, day
    )
    sqlite_session.flush()
    assert first.results[0].accepted == 1
    assert sqlite_session.scalar(
        select(Price).where(Price.security_id == apple.id)
    ).close == Decimal("100")

    provider = FakeProvider({"AAPL": [_bar("AAPL", day, "101")]})
    MarketDataService(sqlite_session, provider).ingest(["AAPL"], day, day)
    sqlite_session.flush()
    prices = list(sqlite_session.scalars(select(Price)))
    assert len(prices) == 1
    assert prices[0].close == Decimal("101")


def test_unknown_ticker_and_invalid_bar_are_skipped(
    sqlite_session: Session,
) -> None:
    _apple(sqlite_session)
    day = date(2024, 1, 2)
    provider = FakeProvider(
        {
            "AAPL": [_bar("AAPL", day, "100", high="50")],
            "MSFT": [_bar("MSFT", day, "200")],
        }
    )
    report = MarketDataService(sqlite_session, provider).ingest(
        ["AAPL", "MSFT"], day, day
    )
    by_ticker = {row.ticker: row for row in report.results}
    assert by_ticker["AAPL"].skipped_invalid == 1
    assert by_ticker["AAPL"].accepted == 0
    assert by_ticker["MSFT"].error == "unknown_ticker"
    assert sqlite_session.scalars(select(Price)).all() == []


def test_provider_error_does_not_abort_other_tickers(
    sqlite_session: Session,
) -> None:
    _apple(sqlite_session)
    msft = Security(
        ticker="MSFT",
        name="Microsoft Corporation",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    sqlite_session.add(msft)
    sqlite_session.flush()
    day = date(2024, 1, 2)
    provider = FakeProvider(
        {"MSFT": [_bar("MSFT", day, "375")]},
        errors={"AAPL": "vendor down"},
    )
    report = run_market_data_ingest(
        sqlite_session,
        tickers=["AAPL", "MSFT"],
        start=day,
        end=day,
        provider=provider,
    )
    assert report.failed_tickers == ["AAPL"]
    assert report.results[1].accepted == 1
    assert sqlite_session.scalar(select(Price.close)) == Decimal("375")


def test_ingest_records_source_and_caps_an_exchange(
    sqlite_session: Session,
) -> None:
    for ticker in ("AAPL", "MSFT"):
        sqlite_session.add(
            Security(
                ticker=ticker,
                name=ticker,
                exchange="NASDAQ",
                sector="Technology",
                currency="USD",
            )
        )
    sqlite_session.flush()
    day = date(2024, 1, 2)
    provider = FakeProvider(
        {
            "AAPL": [_bar("AAPL", day, "100")],
            "MSFT": [_bar("MSFT", day, "50")],
        }
    )
    report = MarketDataService(sqlite_session, provider).ingest(
        None,
        day,
        day,
        exchange="nasdaq",
        max_securities=1,
    )
    assert report.symbols_requested == 2
    assert report.symbols_omitted == 1
    assert [row.ticker for row in report.results] == ["AAPL"]
    stored = sqlite_session.scalar(select(Price))
    assert stored is not None
    assert stored.source == "fake"
    assert stored.ingested_at is not None


class _FlakyProvider(MarketDataProvider):
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def fetch_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> list[RawBar]:
        self.calls += 1
        if self.calls < 3:
            raise ProviderError("rate limit")
        return [_bar(ticker, start, "10")]


def test_provider_error_is_retried_then_accepted(sqlite_session: Session) -> None:
    _apple(sqlite_session)
    day = date(2024, 1, 2)
    provider = _FlakyProvider()
    report = MarketDataService(sqlite_session, provider).ingest(
        ["AAPL"],
        day,
        day,
        max_attempts=3,
        retry_backoff_seconds=0,
    )
    assert provider.calls == 3
    assert report.failed_tickers == []
    assert report.results[0].accepted == 1


class _PermanentProvider(MarketDataProvider):
    name = "permanent"

    def __init__(self) -> None:
        self.calls = 0

    def fetch_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> list[RawBar]:
        self.calls += 1
        raise ProviderError("unknown symbol", retryable=False)


def test_permanent_provider_error_is_not_retried(sqlite_session: Session) -> None:
    _apple(sqlite_session)
    day = date(2024, 1, 2)
    provider = _PermanentProvider()
    report = MarketDataService(sqlite_session, provider).ingest(
        ["AAPL"],
        day,
        day,
        max_attempts=3,
        retry_backoff_seconds=0,
    )
    assert provider.calls == 1
    assert report.failed_tickers == ["AAPL"]
    assert report.results[0].upserted == 0


def test_window_longer_than_the_cap_is_rejected(sqlite_session: Session) -> None:
    provider = FakeProvider({})
    try:
        MarketDataService(sqlite_session, provider).ingest(
            ["AAPL"],
            date(2010, 1, 1),
            date(2024, 1, 1),
            max_window_days=30,
        )
    except ValueError as exc:
        assert "max is 30" in str(exc)
    else:
        raise AssertionError("expected the window cap to reject the request")
