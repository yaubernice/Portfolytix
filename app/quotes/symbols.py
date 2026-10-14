"""Symbols the quote worker should follow.

Watchlist membership is the set. The configured demo list is used only
when no watchlist item exists, so a fresh database still has a quote.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.quotes.factory import quote_symbols
from app.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)
_fallback_logged = False
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")


def load_quote_symbols(
    session: Session | None = None,
) -> list[str]: #load the quote symbols from the database
    owns_session = session is None
    db = session or SessionLocal()
    try:
        tickers = WatchlistRepository(db).distinct_active_tickers(
            limit=settings.quote_max_symbols #limit the number of symbols to load
        )
    except Exception:
        if not owns_session:
            raise
        logger.exception("quote_symbol_load_failed")
        tickers = []
    finally:
        if owns_session:
            db.close()
    global _fallback_logged
    if tickers:
        _fallback_logged = False
        return tickers
    if not _fallback_logged:
        logger.info("quote_symbols_fallback", extra={"reason": "no_watchlist_items"})
        _fallback_logged = True
    return quote_symbols()


def subscription_delta(
    current: set[str],
    wanted: list[str],
) -> tuple[list[str], list[str]]:
    """Symbols to subscribe and unsubscribe. Order of new names follows ``wanted``."""
    target = {symbol.upper() for symbol in wanted}
    added: list[str] = []
    for symbol in wanted:
        normalized = symbol.upper()
        if normalized not in current and normalized not in added:
            added.append(normalized)
    removed = sorted(current - target)
    return added, removed


def normalize_quote_symbols(value: str, *, limit: int) -> list[str]:
    """Normalize a comma-separated API filter and reject ambiguous symbols."""
    symbols: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        symbol = part.strip().upper()
        if not symbol:
            continue
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError(f"Invalid quote ticker: {part.strip()}")
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if len(symbols) > limit:
        raise ValueError(f"At most {limit} quote tickers may be requested")
    return symbols
