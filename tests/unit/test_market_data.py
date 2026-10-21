from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.market_data.alpha_vantage import (
    AlphaVantageProvider,
    parse_alpha_vantage_daily,
)
from app.market_data.errors import ProviderError
from app.market_data.factory import build_provider
from app.market_data.normalize import normalize_bar
from app.market_data.stooq import parse_stooq_csv
from app.market_data.types import RawBar
from app.market_data.yahoo_fundamentals import (
    fetch_latest_quotes,
    parse_yahoo_chart_quote,
    parse_yahoo_quote,
)
from app.market_data.yahoo_history import parse_yahoo_chart


def _raw(**overrides: object) -> RawBar:
    base = RawBar(
        ticker="AAPL",
        day=date(2024, 1, 2),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        adjusted_close=Decimal("105"),
        volume=1_000,
    )
    return replace(base, **overrides)


def test_normalize_accepts_valid_bar() -> None:
    bar, reason = normalize_bar(_raw())
    assert reason is None
    assert bar is not None
    assert bar.timestamp.day == 2
    assert bar.close == Decimal("105")


def test_normalize_drops_broken_ohlc() -> None:
    bar, reason = normalize_bar(_raw(high=Decimal("80"), low=Decimal("90")))
    assert bar is None
    assert reason == "high_below_low"
    bar, reason = normalize_bar(_raw(close=Decimal("0")))
    assert reason == "non_positive_price"
    bar, reason = normalize_bar(_raw(volume=-1))
    assert reason == "negative_volume"


def test_parse_alpha_vantage_daily_filters_range() -> None:
    payload = {
        "Time Series (Daily)": {
            "2024-01-02": {
                "1. open": "100",
                "2. high": "110",
                "3. low": "90",
                "4. close": "105",
                "5. volume": "1000",
            },
            "2023-12-29": {
                "1. open": "1",
                "2. high": "1",
                "3. low": "1",
                "4. close": "1",
                "5. volume": "1",
            },
        }
    }
    bars = parse_alpha_vantage_daily(
        payload, "AAPL", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert len(bars) == 1
    assert bars[0].day == date(2024, 1, 2)
    assert bars[0].adjusted_close == Decimal("105")


def test_adjusted_close_is_used_only_when_the_payload_has_it() -> None:
    payload = {
        "Time Series (Daily)": {
            "2024-01-02": {
                "1. open": "100",
                "2. high": "110",
                "3. low": "90",
                "4. close": "105",
                "5. adjusted close": "99",
                "6. volume": "1000",
            }
        }
    }
    bars = parse_alpha_vantage_daily(
        payload, "AAPL", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert bars[0].close == Decimal("105")
    assert bars[0].adjusted_close == Decimal("99")


def test_long_window_does_not_request_full_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "market_data_allow_full_history", False)
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["outputsize"] = request.url.params["outputsize"]
        return httpx.Response(200, json={"Note": "slow down"})

    provider = AlphaVantageProvider(
        "key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError):
        provider.fetch_daily_bars("AAPL", date(2020, 1, 1), date(2024, 1, 1))
    assert seen["outputsize"] == "compact"


def test_parse_alpha_vantage_rate_limit() -> None:
    with pytest.raises(ProviderError, match="rate-limited"):
        parse_alpha_vantage_daily(
            {"Note": "Please slow down"},
            "AAPL",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )


def test_alpha_vantage_requires_api_key() -> None:
    with pytest.raises(ProviderError, match="MARKET_DATA_API_KEY"):
        AlphaVantageProvider("   ")


def test_parse_stooq_csv() -> None:
    csv = (
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,100,110,90,105,1000\n"
        "2024-01-03,105,106,104,105.5,2000\n"
    )
    bars = parse_stooq_csv(csv, "AAPL", date(2024, 1, 2), date(2024, 1, 2))
    assert len(bars) == 1
    assert bars[0].volume == 1000
    assert bars[0].close == Decimal("105")


def test_parse_yahoo_chart_keeps_the_window_and_skips_a_null_close() -> None:
    inside = int(datetime(2024, 1, 2, 14, 30, tzinfo=UTC).timestamp())
    outside = int(datetime(2023, 12, 29, 14, 30, tzinfo=UTC).timestamp())
    bars = parse_yahoo_chart(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [outside, inside, inside + 86400],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [1, 10.5, 11],
                                    "high": [1, 12, 11],
                                    "low": [1, 10, 11],
                                    "close": [1, 11.25, None],
                                    "volume": [1, 1000, 5],
                                }
                            ]
                        },
                    }
                ]
            }
        },
        "JPM",
        date(2024, 1, 2),
        date(2024, 1, 2),
    )
    assert len(bars) == 1
    assert bars[0].day == date(2024, 1, 2)
    assert bars[0].close == Decimal("11.2500")
    assert bars[0].volume == 1000


def test_yahoo_snapshot_keeps_a_complete_company_and_drops_a_partial_one() -> None:
    from app.market_data.yahoo_fundamentals import parse_yahoo_snapshot

    def payload(**figures: object) -> dict:
        def node(value: object) -> dict:
            return {"raw": value}

        return {
            "quoteSummary": {
                "result": [
                    {
                        "price": {"marketCap": node(figures["market_cap"])},
                        "summaryDetail": {"trailingPE": node(figures["pe"])},
                        "financialData": {
                            "returnOnEquity": node(figures["roe"]),
                            "revenueGrowth": node(figures["growth"]),
                        },
                        "assetProfile": {"sector": figures["sector"]},
                    }
                ]
            }
        }

    parsed = parse_yahoo_snapshot(
        payload(
            market_cap=92_229_208,
            pe=10.98,
            roe=0.09323,
            growth=0.124,
            sector="Financial Services",
        )
    )
    assert parsed is not None
    assert parsed["sector"] == "Financial Services"
    assert parsed["market_cap"] == Decimal("92229208")
    missing = parse_yahoo_snapshot(
        payload(
            market_cap=182_552_464,
            pe=None,
            roe=-0.11,
            growth=0.1,
            sector="Financial Services",
        )
    )
    assert missing is None


def test_yahoo_quote_keeps_the_latest_price() -> None:
    parsed = parse_yahoo_quote(
        {
            "quoteSummary": {
                "result": [
                    {
                        "price": {
                            "regularMarketPrice": {"raw": 189.25},
                            "regularMarketTime": {"raw": 1761000000},
                            "marketCap": {"raw": 2_800_000_000_000},
                        },
                        "summaryDetail": {"trailingPE": {"raw": 31.5}},
                    }
                ]
            }
        }
    )
    assert parsed is not None
    assert parsed["price"] == Decimal("189.25")
    assert parsed["market_cap"] == Decimal("2800000000000")
    assert parsed["pe_ratio"] == Decimal("31.5")
    assert parsed["quoted_at"] == datetime.fromtimestamp(1761000000, UTC)
    assert parse_yahoo_quote({"quoteSummary": {"result": []}}) is None


def test_yahoo_chart_quote_reads_the_latest_price() -> None:
    parsed = parse_yahoo_chart_quote(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 339.5,
                            "regularMarketTime": 1792526401,
                            "chartPreviousClose": 342.94,
                        }
                    }
                ]
            }
        }
    )
    assert parsed is not None
    assert parsed["price"] == Decimal("339.5")
    assert parsed["previous_close"] == Decimal("342.94")
    assert parsed["market_cap"] is None
    assert parsed["quoted_at"] == datetime.fromtimestamp(1792526401, UTC)
    assert parse_yahoo_chart_quote({"chart": {"result": []}}) is None


def test_yahoo_is_a_history_provider() -> None:
    provider = build_provider("yahoo", client=httpx.Client())
    assert provider.name == "yahoo"


def test_latest_quotes_keep_successes_from_the_pool(monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider_quote_workers", 2)

    def fake(symbol: str) -> tuple[str, dict | None]:
        if symbol == "BAD":
            return symbol, None
        return symbol, {
            "price": Decimal("2"),
            "market_cap": None,
            "pe_ratio": None,
            "previous_close": Decimal("1"),
            "quoted_at": None,
        }

    monkeypatch.setattr("app.market_data.yahoo_fundamentals._chart_quote", fake)
    found = fetch_latest_quotes(["AAPL", "BAD", "MSFT", "AAPL"])
    assert set(found) == {"AAPL", "MSFT"}
    assert found["MSFT"]["price"] == Decimal("2")
