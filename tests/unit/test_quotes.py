import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.ai.evidence import attach_live_moves, build_evidence
from app.core.config import settings
from app.core.metrics import MemoryMetrics
from app.market_data.alpha_vantage import (
    parse_alpha_vantage_news,
    parse_alpha_vantage_overview,
    parse_alpha_vantage_quote,
)
from app.market_data.errors import ProviderError
from app.market_data.finnhub import (
    FinnhubQuoteSource,
    parse_finnhub_news,
    parse_finnhub_trades,
)
from app.quotes.models import quote_from_parts
from app.quotes.store import MemoryQuoteStore
from app.services.positions import CostFill, average_cost_positions
from app.workers.quote_worker import publish_heartbeat, stream_finnhub
from tests.unit.test_assistant import _analytics


def test_finnhub_trade_becomes_a_quote() -> None:
    quotes = parse_finnhub_trades(
        {
            "type": "trade",
            "data": [{"s": "AAPL", "p": 251.42, "t": 1_700_000_000_000, "v": 12}],
        }
    )
    assert len(quotes) == 1
    assert quotes[0].ticker == "AAPL"
    assert quotes[0].price == Decimal("251.42")
    assert quotes[0].volume == 12
    assert quotes[0].source == "finnhub"
    assert quotes[0].timeliness == "realtime"


def test_finnhub_ignores_non_trade_frames() -> None:
    assert parse_finnhub_trades({"type": "ping"}) == []


def test_finnhub_trade_parser_keeps_valid_symbols_and_skips_bad_rows() -> None:
    quotes = parse_finnhub_trades(
        {
            "type": "trade",
            "data": [
                {"s": "AAPL", "p": "190.25", "t": 1_700_000_000_000, "v": 1},
                {"s": "BAD", "p": "NaN", "t": 1_700_000_000_000, "v": 1},
                {"s": "", "p": "12", "t": 1_700_000_000_000, "v": 1},
                {"s": "MSFT", "p": "420", "t": 1_700_000_001_000, "v": 2},
            ],
        }
    )
    assert [quote.ticker for quote in quotes] == ["AAPL", "MSFT"]


def test_finnhub_provider_failure_does_not_return_partial_batch() -> None:
    import httpx
    import pytest

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["symbol"] == "AAPL":
            return httpx.Response(200, json={"c": 190, "pc": 185, "t": 1_700_000_000})
        return httpx.Response(503, json={"detail": "down"})

    source = FinnhubQuoteSource(
        "key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError):
        source.fetch_quotes(["AAPL", "MSFT"])


def test_stale_realtime_quote_is_never_exposed_as_realtime() -> None:
    store = MemoryQuoteStore()
    store.publish(
        quote_from_parts(
            ticker="AAPL",
            price=Decimal("100"),
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source="finnhub",
            timeliness="realtime",
        )
    )
    quote = store.snapshot()[0]
    assert quote.timeliness == "stale"
    assert quote.provider_timeliness == "realtime"
    assert quote.is_stale is True
    assert quote.age_seconds > 0
    assert quote.provider_timestamp == datetime(2026, 1, 1, tzinfo=UTC)
    assert quote.received_at is not None


def test_simulator_quote_becomes_stale_when_its_print_is_old() -> None:
    quote = quote_from_parts(
        ticker="AAPL",
        price=Decimal("100"),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source="simulator",
        timeliness="simulated",
    ).freshened(now=datetime(2026, 1, 2, tzinfo=UTC), max_age_seconds=1)
    assert quote.timeliness == "stale"
    assert quote.provider_timeliness == "simulated"
    assert quote.is_stale is True


def test_delayed_quote_keeps_its_label_when_the_print_is_old() -> None:
    now = datetime(2026, 10, 15, 15, tzinfo=UTC)
    quote = quote_from_parts(
        ticker="MSFT",
        price=Decimal("100"),
        timestamp=datetime(2026, 10, 14, tzinfo=UTC),
        source="alpha_vantage",
        timeliness="delayed",
        received_at=now,
    ).freshened(now=now)
    assert quote.timeliness == "delayed"
    assert quote.provider_timeliness == "delayed"
    assert quote.is_stale is False
    assert quote.age_seconds > 0


def test_delayed_quote_is_stale_when_the_refresh_is_old() -> None:
    now = datetime(2026, 10, 15, 15, tzinfo=UTC)
    quote = quote_from_parts(
        ticker="MSFT",
        price=Decimal("100"),
        timestamp=now,
        source="alpha_vantage",
        timeliness="delayed",
        received_at=datetime(2026, 10, 15, 14, tzinfo=UTC),
    ).freshened(now=now, max_age_seconds=60)
    assert quote.timeliness == "stale"
    assert quote.provider_timeliness == "delayed"


def test_quote_worker_heartbeat_has_operational_state() -> None:
    store = MemoryQuoteStore()
    published = datetime(2026, 10, 14, tzinfo=UTC)
    publish_heartbeat(
        store,
        provider="simulator",
        symbols=["AAPL", "MSFT"],
        last_publish_at=published,
        last_poll_at=published,
    )
    heartbeat = store.get_worker_heartbeat()
    assert heartbeat is not None
    assert heartbeat["provider"] == "simulator"
    assert heartbeat["symbol_count"] == 2
    assert heartbeat["active_subscriptions"] == ["AAPL", "MSFT"]
    assert heartbeat["last_publish_at"] == published.isoformat()


def test_alpha_vantage_global_quote() -> None:
    quote = parse_alpha_vantage_quote(
        {
            "Global Quote": {
                "01. symbol": "MSFT",
                "05. price": "420.10",
                "06. volume": "1000",
                "07. latest trading day": "2026-10-02",
                "08. previous close": "418.00",
            }
        },
        "MSFT",
    )
    assert quote.price == Decimal("420.10")
    assert quote.change == Decimal("2.10")
    assert quote.source == "alpha_vantage"
    assert quote.timeliness == "delayed"
    fresh = quote.freshened()
    assert fresh.timeliness == "delayed"
    assert fresh.is_stale is False


def test_overview_maps_optional_fields() -> None:
    fields = parse_alpha_vantage_overview(
        {
            "Symbol": "AAPL",
            "EPS": "6.10",
            "RevenueTTM": "400000000000",
            "ProfitMargin": "0.25",
            "DividendYield": "0.004",
            "Beta": "1.2",
            "EBITDA": "120000000000",
            "ReturnOnAssetsTTM": "0.20",
            "QuarterlyEarningsGrowthYOY": "0.11",
            "PERatio": "28",
            "ReturnOnEquityTTM": "0.35",
            "QuarterlyRevenueGrowthYOY": "0.08",
            "MarketCapitalization": "3500000000000",
        },
        "AAPL",
    )
    assert fields["eps"] == Decimal("6.10")
    assert fields["beta"] == Decimal("1.2")
    assert fields["market_cap"] == Decimal("3500000000000")
    assert fields["ebitda"] == Decimal("120000000000")
    assert fields["roa"] == Decimal("0.20")
    assert fields["earnings_growth"] == Decimal("0.11")
    assert "debt_equity" not in fields


def test_news_parsers_keep_headline_fields() -> None:
    finnhub = parse_finnhub_news(
        [
            {
                "headline": "Apple updates guidance",
                "summary": "Short",
                "source": "Reuters",
                "url": "https://example.test/a",
                "datetime": 1_700_000_000,
            }
        ]
    )
    assert finnhub[0]["headline"] == "Apple updates guidance"
    assert finnhub[0]["provider"] == "finnhub"
    assert finnhub[0]["sentiment"] is None
    alpha = parse_alpha_vantage_news(
        {
            "feed": [
                {
                    "title": "Chip demand",
                    "summary": "x" * 600,
                    "source": "Example",
                    "url": "https://example.test/b",
                    "time_published": "20261002T120000",
                    "overall_sentiment_label": "Bullish",
                    "ticker_sentiment": [{"ticker": "AMD"}],
                }
            ]
        },
        "NVDA",
    )
    assert alpha[0]["headline"] == "Chip demand"
    assert alpha[0]["provider"] == "alpha_vantage"
    assert alpha[0]["sentiment"] == "Bullish"
    assert alpha[0]["tickers"] == ["NVDA", "AMD"]
    assert len(alpha[0]["summary"]) == 500
    assert "content" not in alpha[0]


def test_average_cost_reduces_on_sell() -> None:
    security_id = uuid4()
    rows = average_cost_positions(
        [
            CostFill(security_id, "AAPL", "BUY", Decimal("10"), Decimal("100")),
            CostFill(security_id, "AAPL", "BUY", Decimal("10"), Decimal("120")),
            CostFill(security_id, "AAPL", "SELL", Decimal("5"), Decimal("130")),
        ]
    )
    assert len(rows) == 1
    assert rows[0].quantity == Decimal("15")
    assert rows[0].avg_cost == Decimal("110")


def test_live_moves_rank_day_change_without_touching_facts() -> None:
    analytics = _analytics([Decimal("0.01")])
    evidence = build_evidence(analytics)
    quote = quote_from_parts(
        ticker="AAPL",
        price=Decimal("111"),
        previous_close=Decimal("110"),
        timestamp=datetime(2026, 10, 3, tzinfo=UTC),
        source="simulator",
    )
    updated = attach_live_moves(evidence, analytics, [quote])
    metrics = {item["name"]: item["value"] for item in updated["metrics"]}
    assert metrics["largest_gainer"].startswith("AAPL ")
    assert metrics["day_change:AAPL"]
    assert updated["facts"] == evidence["facts"]


def test_finnhub_stream_backs_off_after_a_dropped_socket(monkeypatch) -> None:
    metrics = MemoryMetrics()
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def fail_then_cancel(_api_key, _symbols, _store) -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("dropped")
        raise asyncio.CancelledError

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(settings, "quote_reconnect_seconds", 2.0)
    monkeypatch.setattr(
        "app.workers.quote_worker.get_metrics",
        lambda: metrics,
    )
    monkeypatch.setattr(
        "app.workers.quote_worker.load_quote_symbols",
        lambda: ["AAPL"],
    )
    monkeypatch.setattr(
        "app.workers.quote_worker._stream_session",
        fail_then_cancel,
    )
    monkeypatch.setattr("app.workers.quote_worker.asyncio.sleep", record_sleep)

    try:
        asyncio.run(stream_finnhub("token", None))
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("stream should stop when the task is cancelled")

    assert attempts["count"] == 3
    assert sleeps == [2.0, 4.0]
    assert metrics.snapshot()["quotes.reconnects"] == 2.0
