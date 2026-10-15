"""US exchange listings from the Nasdaq Trader symbol directory.

The files name listed symbols. They do not include sector, fundamentals,
prices, or news. Missing fields stay blank.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Security
from app.market_data.errors import ProviderError

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
_OTHER_EXCHANGES = {
    "A": ("NYSE American", "XASE"),
    "N": ("NYSE", "XNYS"),
    "P": ("NYSE Arca", "ARCX"),
    "Z": ("Cboe", "BATS"),
    "V": ("IEX", "IEXG"),
}


@dataclass(frozen=True, slots=True)
class Listing:
    ticker: str
    name: str
    exchange: str
    mic: str
    asset_type: str


def parse_nasdaq_listed(text: str) -> list[Listing]:
    """Nasdaq-listed names. Test issues are skipped."""
    rows = _lines(text)
    if not rows or not rows[0].startswith("Symbol|"):
        raise ProviderError("Nasdaq listed file has no header", retryable=False)
    listings: list[Listing] = []
    for parts in rows[1:]:
        fields = parts.split("|")
        if len(fields) < 8 or fields[0].startswith("File Creation Time"):
            continue
        if fields[3].strip().upper() == "Y":
            continue
        ticker = fields[0].strip().upper()
        name = _name(fields[1])
        if not _SYMBOL.match(ticker) or not name:
            continue
        if fields[6].strip().upper() == "Y":
            asset_type = "etf"
        elif fields[7].strip().upper() == "Y":
            asset_type = "fund"
        else:
            asset_type = "equity"
        listings.append(
            Listing(ticker, name, "NASDAQ", "XNAS", asset_type)
        )
    return listings


def parse_other_listed(text: str) -> list[Listing]:
    """NYSE, NYSE American, NYSE Arca, Cboe, and IEX names."""
    rows = _lines(text)
    if not rows or not rows[0].startswith("ACT Symbol|"):
        raise ProviderError("Other listed file has no header", retryable=False)
    listings: list[Listing] = []
    for parts in rows[1:]:
        fields = parts.split("|")
        if len(fields) < 8 or fields[0].startswith("File Creation Time"):
            continue
        if fields[6].strip().upper() == "Y":
            continue
        venue = _OTHER_EXCHANGES.get(fields[2].strip().upper())
        if venue is None:
            continue
        ticker = fields[0].strip().upper()
        name = _name(fields[1])
        if not _SYMBOL.match(ticker) or not name:
            continue
        asset_type = "etf" if fields[4].strip().upper() == "Y" else "equity"
        exchange, mic = venue
        listings.append(Listing(ticker, name, exchange, mic, asset_type))
    return listings


def merge_listings(*groups: list[Listing]) -> list[Listing]:
    """First file wins when the same ticker appears twice."""
    seen: set[str] = set()
    merged: list[Listing] = []
    for group in groups:
        for row in group:
            if row.ticker in seen:
                continue
            seen.add(row.ticker)
            merged.append(row)
    return merged


def apply_listings(session: Session, listings: list[Listing]) -> tuple[int, int]:
    """Insert listings that are not already stored. Retire BENCH placeholders."""
    existing = set(session.scalars(select(Security.ticker)))
    added = 0
    for row in listings:
        if row.ticker in existing:
            continue
        session.add(
            Security(
                ticker=row.ticker,
                name=row.name,
                exchange=row.exchange,
                mic=row.mic,
                sector="",
                country="US",
                currency="USD",
                asset_type=row.asset_type,
                provider="nasdaq",
                provider_symbol=row.ticker,
                is_active=True,
            )
        )
        existing.add(row.ticker)
        added += 1
    retired = int(
        session.execute(
            update(Security)
            .where(
                Security.ticker.like("BENCH%"),
                Security.is_active.is_(True),
            )
            .values(is_active=False)
        ).rowcount
        or 0
    )
    session.flush()
    return added, retired


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _name(value: str) -> str:
    name = " ".join(value.split())
    return name[:200]
