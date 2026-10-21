"""Yahoo Finance headline search. No API key. No invented article text."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.market_data.capabilities import YAHOO_NEWS
from app.market_data.errors import ProviderError
from app.market_data.news import news_record

YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"


def parse_yahoo_news(payload: dict, ticker: str) -> list[dict]:
    """Keep stories that name this ticker. Photos are optional."""
    rows = payload.get("news")
    if not isinstance(rows, list):
        raise ProviderError(
            f"Yahoo news for {ticker} has no news list",
            retryable=False,
        )
    symbol = ticker.strip().upper()
    items: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("type") not in (None, "STORY"):
            continue
        headline = row.get("title")
        if not isinstance(headline, str) or not headline.strip():
            continue
        related = _tickers(row.get("relatedTickers"))
        if related and symbol not in related:
            continue
        published = row.get("providerPublishTime")
        try:
            unix = int(published)
            stamp = (
                datetime.fromtimestamp(unix, tz=UTC).isoformat() if unix > 0 else ""
            )
        except (TypeError, ValueError, OSError):
            stamp = ""
        source = row.get("publisher")
        publisher = (
            source.strip()
            if isinstance(source, str) and source.strip()
            else "Yahoo Finance"
        )
        summary = row.get("summary")
        if not isinstance(summary, str):
            summary = ""
        items.append(
            news_record(
                headline=headline,
                summary=summary,
                source=publisher,
                url=str(row.get("link") or ""),
                published_at=stamp,
                tickers=related or [symbol],
                sentiment=None,
                provider="yahoo",
                image_url=_image(row.get("thumbnail")),
            )
        )
    return items


class YahooNewsSource:
    """Public search feed. A summary is kept only when the payload includes one."""

    name = "yahoo"
    capabilities = YAHOO_NEWS

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0)

    def fetch_news(self, ticker: str) -> list[dict]:
        symbol = ticker.strip().upper()
        if not symbol:
            raise ProviderError("Yahoo news ticker is empty", retryable=False)
        response = self._client.get(
            YAHOO_SEARCH,
            params={"q": symbol, "quotesCount": 0, "newsCount": 12},
            headers={"User-Agent": "Portfolytix/1.0"},
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Yahoo news error for {symbol}") from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                f"Yahoo news for {symbol} is not an object",
                retryable=False,
            )
        return parse_yahoo_news(payload, symbol)[:6]


def _tickers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    symbols: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        symbol = item.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _image(thumbnail: object) -> str:
    if not isinstance(thumbnail, dict):
        return ""
    resolutions = thumbnail.get("resolutions")
    if not isinstance(resolutions, list):
        return ""
    best = ""
    best_width = -1
    for row in resolutions:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        if len(url) > 1000:
            continue
        if row.get("tag") == "original":
            return url
        width = row.get("width") if isinstance(row.get("width"), int) else 0
        if width > best_width:
            best = url
            best_width = width
    return best
