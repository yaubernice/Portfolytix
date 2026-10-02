"""Stooq daily CSV adapter. No API key. US symbols use the ``.us`` suffix."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO

import httpx

from app.market_data.errors import ProviderError
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar

BASE_URL = "https://stooq.com/q/d/l/"


class StooqProvider(MarketDataProvider):
    name = "stooq"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0)

    def fetch_daily_bars(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> list[RawBar]:
        symbol = ticker.upper()
        stooq_symbol = f"{symbol.lower()}.us"
        response = self._client.get(BASE_URL, params={"s": stooq_symbol, "i": "d"})
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Stooq HTTP error for {symbol}") from exc
        return parse_stooq_csv(response.text, symbol, start, end)


def parse_stooq_csv(
    text: str,
    ticker: str,
    start: date,
    end: date,
) -> list[RawBar]:
    """Parse Stooq daily CSV. No HTTP here so tests stay offline."""
    stripped = text.strip()
    if not stripped or stripped.lower().startswith("no data"):
        raise ProviderError(f"Stooq returned no data for {ticker}")

    bars: list[RawBar] = []
    reader = StringIO(stripped)
    header = reader.readline()
    if "date" not in header.lower():
        raise ProviderError(f"Stooq CSV missing header for {ticker}")
    for line in reader:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            day = date.fromisoformat(parts[0])
        except ValueError:
            continue
        if day < start or day > end:
            continue
        try:
            close = Decimal(parts[4])
            volume_text = parts[5] if parts[5] else "0"
            bars.append(
                RawBar(
                    ticker=ticker,
                    day=day,
                    open=Decimal(parts[1]),
                    high=Decimal(parts[2]),
                    low=Decimal(parts[3]),
                    close=close,
                    adjusted_close=close,
                    volume=int(Decimal(volume_text)),
                )
            )
        except (InvalidOperation, ArithmeticError, ValueError):
            continue
    bars.sort(key=lambda bar: bar.day)
    return bars
