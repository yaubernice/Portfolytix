"""Latest provider prices for marks and trades. Not stored as daily bars.

A fresh Yahoo print is kept in the quote store. The next reader reuses it
until the key expires. A simulated print is not reused.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.core.config import settings
from app.market_data.yahoo_fundamentals import fetch_latest_quotes
from app.quotes.models import LiveQuote, quote_from_parts
from app.quotes.store import QuoteStore, QuoteStoreError, build_quote_store

logger = logging.getLogger(__name__)


def provider_quotes(
    tickers: list[str],
    store: QuoteStore | None = None,
    *,
    refresh: bool = False,
) -> dict[str, LiveQuote]:
    """Yahoo's latest published price for each symbol. A miss is omitted."""
    if not settings.provider_marks or not tickers:
        return {}
    symbols: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        return {}
    quotes = build_quote_store() if store is None else store
    cached = {} if refresh else _cached_yahoo(quotes, symbols)
    missing = [symbol for symbol in symbols if symbol not in cached]
    if not missing:
        return cached
    try:
        fetched = fetch_latest_quotes(missing)
    except Exception:
        logger.warning("provider_quote_failed")
        return cached
    received_at = datetime.now(UTC)
    for ticker, row in fetched.items():
        quoted_at = row.get("quoted_at") or received_at
        quote = quote_from_parts(
            ticker=ticker,
            price=row["price"],
            timestamp=quoted_at,
            source="yahoo",
            previous_close=row.get("previous_close"),
            timeliness="delayed",
            received_at=received_at,
        )
        cached[ticker] = quote
        try:
            quotes.publish(quote, ttl_seconds=settings.provider_mark_ttl_seconds)
        except QuoteStoreError:
            logger.warning("provider_quote_cache_failed", extra={"ticker": ticker})
    return {symbol: cached[symbol] for symbol in symbols if symbol in cached}


def _cached_yahoo(store: QuoteStore, symbols: list[str]) -> dict[str, LiveQuote]:
    wanted = set(symbols)
    cached: dict[str, LiveQuote] = {}
    try:
        rows = store.snapshot(symbols)
    except Exception:
        logger.warning("provider_quote_cache_read_failed")
        return {}
    for quote in rows:
        if quote.ticker not in wanted:
            continue
        if quote.source != "yahoo" or quote.is_stale:
            continue
        cached[quote.ticker] = quote
    if cached:
        logger.info("provider_quote_cache_hit", extra={"count": len(cached)})
    return cached
