from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RawBar: #not yet passed validation rules
    """Vendor-normalized OHLCV before Portfolytix validation."""

    ticker: str
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int


# ticker is not stored; upsert keys off security_id + timestamp
@dataclass(frozen=True, slots=True)
class NormalizedBar: #ready to be written to PostgreSQL for database storage
    """A bar that passed checks and is ready to upsert."""

    day: date
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int
