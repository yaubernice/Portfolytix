"""Alpha Vantage TIME_SERIES_DAILY adapter.

Free daily bars do not include split-adjusted close; we store
``adjusted_close = close`` and document that. The API key is never logged.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx

from app.market_data.errors import ProviderError
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar

BASE_URL = "https://www.alphavantage.co/query"
SERIES_KEY = "Time Series (Daily)"


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderError(
                "MARKET_DATA_API_KEY is empty; "
                "set it or use MARKET_DATA_PROVIDER=stooq"
            )
        self._api_key = api_key.strip()
        self._client = client or httpx.Client(timeout=30.0)

    def fetch_daily_bars(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> list[RawBar]:
        symbol = ticker.upper()
        span = (end - start).days
        payload = self._get_json(
            symbol,
            outputsize="full" if span > 90 else "compact",
        )
        return parse_alpha_vantage_daily(payload, symbol, start, end)

    def _get_json(self, symbol: str, outputsize: str) -> dict:
        response = self._client.get(
            BASE_URL,
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": outputsize,
                "apikey": self._api_key,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Alpha Vantage HTTP error for {symbol}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                f"Alpha Vantage returned non-JSON for {symbol}"
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError(f"Alpha Vantage payload is not an object for {symbol}")
        return payload


def parse_alpha_vantage_daily(
    payload: dict,
    ticker: str,
    start: date,
    end: date,
) -> list[RawBar]:
    """Turn a TIME_SERIES_DAILY JSON body into RawBar rows. No HTTP here."""
    if payload.get("Note") or payload.get("Information"):
        raise ProviderError(
            f"Alpha Vantage rate-limited or blocked for {ticker}"
        )
    error = payload.get("Error Message")
    if error:
        raise ProviderError(f"Alpha Vantage rejected {ticker}: {error}")
    series = payload.get(SERIES_KEY)
    if not isinstance(series, dict):
        raise ProviderError(f"Alpha Vantage missing time series for {ticker}")

    bars: list[RawBar] = []
    for day_text, fields in series.items():
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day < start or day > end:
            continue
        if not isinstance(fields, dict):
            continue
        try:
            close = Decimal(str(fields["4. close"]))
            bars.append(
                RawBar(
                    ticker=ticker,
                    day=day,
                    open=Decimal(str(fields["1. open"])),
                    high=Decimal(str(fields["2. high"])),
                    low=Decimal(str(fields["3. low"])),
                    close=close,
                    adjusted_close=close,
                    volume=int(Decimal(str(fields["5. volume"]))),
                )
            )
        except (KeyError, ArithmeticError, ValueError):
            continue
    bars.sort(key=lambda bar: bar.day)
    return bars
