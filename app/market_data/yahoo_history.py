"""Yahoo Finance daily chart. No API key. Bars are historical, not live quotes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.market_data.capabilities import YAHOO_HISTORY
from app.market_data.errors import ProviderError
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def parse_yahoo_chart(
    payload: dict,
    ticker: str,
    start: date,
    end: date,
) -> list[RawBar]:
    """Keep daily bars inside the requested window. Missing prints are skipped."""
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise ProviderError(
            f"Yahoo history for {ticker} is not an object",
            retryable=False,
        )
    if chart.get("error"):
        raise ProviderError(
            f"Yahoo history for {ticker} returned no bars",
            retryable=False,
        )
    rows = chart.get("result")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise ProviderError(
            f"Yahoo history for {ticker} has no result",
            retryable=False,
        )
    result = rows[0]
    stamps = result.get("timestamp")
    indicators = result.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    if not isinstance(stamps, list) or not isinstance(quotes, list) or not quotes:
        raise ProviderError(
            f"Yahoo history for {ticker} has no daily bars",
            retryable=False,
        )
    quote = quotes[0] if isinstance(quotes[0], dict) else {}
    adjusted = _adjusted(indicators)
    bars: list[RawBar] = []
    for index, stamp in enumerate(stamps):
        try:
            day = datetime.fromtimestamp(int(stamp), tz=UTC).date()
        except (TypeError, ValueError, OSError):
            continue
        if day < start or day > end:
            continue
        close = _price(_at(quote.get("close"), index))
        if close is None:
            continue
        open_ = _price(_at(quote.get("open"), index)) or close
        high = _price(_at(quote.get("high"), index)) or close
        low = _price(_at(quote.get("low"), index)) or close
        adj = _price(_at(adjusted, index)) or close
        volume = _volume(_at(quote.get("volume"), index))
        bars.append(
            RawBar(
                ticker=ticker,
                day=day,
                open=open_,
                high=max(high, open_, close, low),
                low=min(low, open_, close, high),
                close=close,
                adjusted_close=adj,
                volume=volume,
            )
        )
    return bars


class YahooHistoryProvider(MarketDataProvider):
    name = "yahoo"
    capabilities = YAHOO_HISTORY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0)

    def fetch_daily_bars(self, ticker: str, start: date, end: date) -> list[RawBar]:
        symbol = ticker.strip().upper()
        if not symbol:
            raise ProviderError("Yahoo history ticker is empty", retryable=False)
        response = self._client.get(
            YAHOO_CHART.format(symbol=symbol),
            params={"interval": "1d", "range": "2y"},
            headers={"User-Agent": "FinSight/1.0"},
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Yahoo history error for {symbol}") from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                f"Yahoo history for {symbol} is not an object",
                retryable=False,
            )
        return parse_yahoo_chart(payload, symbol, start, end)


def _at(values: object, index: int) -> object:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _adjusted(indicators: object) -> list:
    if not isinstance(indicators, dict):
        return []
    rows = indicators.get("adjclose")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return []
    values = rows[0].get("adjclose")
    return values if isinstance(values, list) else []


def _price(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return number.quantize(Decimal("0.0001"))


def _volume(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    try:
        volume = int(value)
    except (TypeError, ValueError):
        return 0
    return volume if volume > 0 else 0
