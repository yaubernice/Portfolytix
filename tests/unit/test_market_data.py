from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.market_data.alpha_vantage import (
    AlphaVantageProvider,
    parse_alpha_vantage_daily,
)
from app.market_data.errors import ProviderError
from app.market_data.normalize import normalize_bar
from app.market_data.stooq import parse_stooq_csv
from app.market_data.types import RawBar


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
