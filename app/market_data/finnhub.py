"""Finnhub trade stream and REST quote parser.

The websocket sends trades (symbol, price, timestamp, volume). Those updates
become the latest Redis quote. They are not inserted into PostgreSQL.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.market_data.capabilities import FINNHUB
from app.market_data.errors import ProviderError
from app.market_data.news import news_record
from app.quotes.models import LiveQuote, quote_from_parts

FINNHUB_REST = "https://finnhub.io/api/v1"
FINNHUB_WS = "wss://ws.finnhub.io"


def parse_finnhub_trades(payload: dict) -> list[LiveQuote]:
    """Parse one Finnhub websocket message. Non-trade frames yield nothing."""
    if payload.get("type") != "trade":
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    quotes: list[LiveQuote] = []
    for trade in data:
        if not isinstance(trade, dict):
            continue
        try:
            millis = int(trade["t"])
            price = Decimal(str(trade["p"]))
            if price <= 0 or not price.is_finite() or millis <= 0:
                continue
            ticker = str(trade["s"]).strip().upper()
            if not ticker:
                continue
            quotes.append(
                quote_from_parts(
                    ticker=ticker,
                    price=price,
                    volume=int(trade["v"]) if trade.get("v") is not None else None,
                    timestamp=datetime.fromtimestamp(millis / 1000, tz=UTC),
                    source="finnhub",
                    timeliness="realtime",
                )
            )
        except (KeyError, ArithmeticError, TypeError, ValueError, OSError):
            continue
    return quotes


def parse_finnhub_quote(payload: dict, ticker: str) -> LiveQuote:
    """Parse the REST `/quote` object. `c` is the current price."""
    try:
        price = Decimal(str(payload["c"]))
        previous = Decimal(str(payload["pc"])) if payload.get("pc") not in (
            None,
            0,
            "0",
        ) else None
        unix = int(payload["t"])
    except (KeyError, ArithmeticError, TypeError, ValueError) as exc:
        raise ProviderError(f"Finnhub quote for {ticker} is missing a price") from exc
    if price <= 0 or not price.is_finite():
        raise ProviderError(f"Finnhub quote for {ticker} has no last price")
    volume = None
    return quote_from_parts(
        ticker=ticker,
        price=price,
        previous_close=previous,
        volume=volume,
        timestamp=datetime.fromtimestamp(unix, tz=UTC) if unix else datetime.now(UTC),
        source="finnhub",
        # REST /quote is not the trade stream, so it is not labeled realtime.
        timeliness="delayed",
    )


def parse_finnhub_news(payload: list, ticker: str = "") -> list[dict]:
    items: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        headline = row.get("headline")
        if not isinstance(headline, str) or not headline.strip():
            continue
        published = row.get("datetime")
        try:
            stamp = datetime.fromtimestamp(int(published), tz=UTC).isoformat()
        except (TypeError, ValueError, OSError):
            stamp = ""
        items.append(
            news_record(
                headline=headline,
                summary=str(row.get("summary") or ""),
                source=str(row.get("source") or "finnhub"),
                url=str(row.get("url") or ""),
                published_at=stamp,
                tickers=[ticker] if ticker else [],
                sentiment=None,
                provider="finnhub",
            )
        )
    return items


class FinnhubQuoteSource:
    name = "finnhub"
    capabilities = FINNHUB

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderError(
                "FINNHUB_API_KEY is empty; set it or use QUOTE_PROVIDER=simulator"
            )
        self._api_key = api_key.strip()
        self._client = client or httpx.Client(timeout=20.0)

    def fetch_quotes(self, tickers: list[str]) -> list[LiveQuote]:
        quotes: list[LiveQuote] = []
        for ticker in tickers:
            symbol = ticker.upper()
            response = self._client.get(
                f"{FINNHUB_REST}/quote",
                params={"symbol": symbol, "token": self._api_key},
            )
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderError(f"Finnhub HTTP error for {symbol}") from exc
            if not isinstance(payload, dict):
                raise ProviderError(f"Finnhub quote for {symbol} is not an object")
            quotes.append(parse_finnhub_quote(payload, symbol))
        return quotes

    def fetch_news(self, ticker: str, start: str, end: str) -> list[dict]:
        symbol = ticker.upper()
        response = self._client.get(
            f"{FINNHUB_REST}/company-news",
            params={
                "symbol": symbol,
                "from": start,
                "to": end,
                "token": self._api_key,
            },
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Finnhub news error for {symbol}") from exc
        if not isinstance(payload, list):
            raise ProviderError(f"Finnhub news for {symbol} is not a list")
        return parse_finnhub_news(payload, symbol)


def finnhub_subscribe_frame(symbol: str) -> str:
    return json.dumps({"type": "subscribe", "symbol": symbol.upper()})


def finnhub_unsubscribe_frame(symbol: str) -> str:
    return json.dumps({"type": "unsubscribe", "symbol": symbol.upper()})
