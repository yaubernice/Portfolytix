"""Idempotent seed of reference securities and synthetic daily bars.

No live market-data API. Prices are a deterministic random walk so tests
and local demos stay reproducible. These seven rows are demo listings,
not the product universe. Re-running the seed upserts them by
provider + provider_symbol and skips price rows that already exist.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import queue_version_bump
from app.db.models import Fundamental, Price, Security, User

logger = logging.getLogger(__name__)

PRICE_SCALE = Decimal("0.000001")
SEED_START = date(2024, 1, 2)
SEED_END = date(2025, 12, 31)
INSERT_CHUNK = 500
DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEMO_USER_EMAIL = "demo@finsight.local"


@dataclass(frozen=True)
class SecuritySpec:
    ticker: str
    name: str
    exchange: str
    sector: str
    currency: str
    start_price: Decimal
    rng_seed: int


def _spec(
    ticker: str,
    name: str,
    sector: str,
    start_price: str,
    rng_seed: int,
) -> SecuritySpec:
    return SecuritySpec(
        ticker=ticker,
        name=name,
        exchange="NASDAQ",
        sector=sector,
        currency="USD",
        start_price=Decimal(start_price),
        rng_seed=rng_seed,
    )


SECURITIES: tuple[SecuritySpec, ...] = (
    _spec("AAPL", "Apple Inc.", "Technology", "185.00", 11),
    _spec("MSFT", "Microsoft Corporation", "Technology", "375.00", 22),
    _spec("NVDA", "NVIDIA Corporation", "Technology", "480.00", 33),
    _spec("AMZN", "Amazon.com, Inc.", "Consumer Discretionary", "150.00", 44),
    _spec("GOOGL", "Alphabet Inc. Class A", "Communication Services", "140.00", 55),
    _spec("META", "Meta Platforms, Inc.", "Communication Services", "350.00", 66),
    _spec("TSLA", "Tesla, Inc.", "Consumer Discretionary", "250.00", 77),
)

# Synthetic latest snapshots, not live filings. Units:
# roe / revenue_growth are decimals (0.15 = 15%). pe_ratio is a multiple.
# market_cap is USD. Chosen so the README example screen returns GOOGL+META.
FUNDAMENTAL_AS_OF = date(2025, 12, 31)
FUNDAMENTALS: dict[str, dict[str, str]] = {
    "AAPL": {
        "roe": "0.35",
        "pe_ratio": "28",
        "revenue_growth": "0.08",
        "market_cap": "3500000000000",
    },
    "MSFT": {
        "roe": "0.38",
        "pe_ratio": "32",
        "revenue_growth": "0.14",
        "market_cap": "3100000000000",
    },
    "NVDA": {
        "roe": "0.70",
        "pe_ratio": "45",
        "revenue_growth": "0.80",
        "market_cap": "2200000000000",
    },
    "AMZN": {
        "roe": "0.18",
        "pe_ratio": "35",
        "revenue_growth": "0.11",
        "market_cap": "1800000000000",
    },
    "GOOGL": {
        "roe": "0.28",
        "pe_ratio": "22",
        "revenue_growth": "0.12",
        "market_cap": "2000000000000",
    },
    "META": {
        "roe": "0.32",
        "pe_ratio": "24",
        "revenue_growth": "0.16",
        "market_cap": "1200000000000",
    },
    "TSLA": {
        "roe": "0.12",
        "pe_ratio": "55",
        "revenue_growth": "0.05",
        "market_cap": "700000000000",
    },
}


def iter_weekdays(start: date, end: date) -> Iterator[date]:
    """Inclusive weekday range. Exchange holidays are ignored on purpose."""
    current = start
    one_day = timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += one_day


def _money(value: Decimal) -> Decimal:
    quantized = value.quantize(PRICE_SCALE, rounding=ROUND_HALF_EVEN)
    if quantized <= 0:
        return PRICE_SCALE
    return quantized


def generate_daily_bars(
    *,
    start: date,
    end: date,
    start_price: Decimal,
    rng_seed: int,
) -> list[dict[str, object]]:
    """Build weekday OHLCV rows. Same inputs always produce the same bars."""
    rng = random.Random(rng_seed)
    prev = _money(start_price)
    rows: list[dict[str, object]] = []
    for day in iter_weekdays(start, end):
        daily_return = Decimal(str(rng.gauss(0.0004, 0.015)))
        close = _money(prev * (Decimal("1") + daily_return))
        open_move = Decimal(str(rng.gauss(0, 0.004)))
        open_ = _money(prev * (Decimal("1") + open_move))
        high_bump = abs(Decimal(str(rng.gauss(0, 0.006))))
        low_bump = abs(Decimal(str(rng.gauss(0, 0.006))))
        high = _money(max(open_, close) * (Decimal("1") + high_bump))
        low = _money(min(open_, close) * (Decimal("1") - low_bump))
        if high < low:
            high, low = low, high
        rows.append(
            {
                "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "adjusted_close": close,
                "volume": rng.randint(15_000_000, 90_000_000),
            }
        )
        prev = close
    return rows


def seed_demo_user(session: Session) -> UUID:
    """Stable demo user so local API calls can set ``user_id`` before auth."""
    stmt = (
        insert(User)
        .values(
            id=DEMO_USER_ID,
            email=DEMO_USER_EMAIL,
            password_hash="not-a-real-hash",
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    session.execute(stmt)
    return DEMO_USER_ID


def seed_market_data(
    session: Session,
    *,
    start: date = SEED_START,
    end: date = SEED_END,
) -> dict[str, int | str]:
    """Insert/update the seven reference tickers and their synthetic bars."""
    demo_user_id = seed_demo_user(session)
    securities_upserted = 0
    for spec in SECURITIES:
        stmt = (
            insert(Security)
            .values(
                ticker=spec.ticker,
                name=spec.name,
                exchange=spec.exchange,
                mic="XNAS",
                sector=spec.sector,
                country="US",
                currency=spec.currency,
                asset_type="equity",
                provider="seed",
                provider_symbol=spec.ticker,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=["provider", "provider_symbol"],
                set_={
                    "name": spec.name,
                    "exchange": spec.exchange,
                    "mic": "XNAS",
                    "sector": spec.sector,
                    "country": "US",
                    "currency": spec.currency,
                    "asset_type": "equity",
                    "is_active": True,
                    "updated_at": func.now(),
                },
            )
        )
        session.execute(stmt)
        securities_upserted += 1

    session.flush()

    prices_inserted = 0
    for spec in SECURITIES:
        security_id = session.execute(
            select(Security.id).where(Security.ticker == spec.ticker)
        ).scalar_one()
        bars = generate_daily_bars(
            start=start,
            end=end,
            start_price=spec.start_price,
            rng_seed=spec.rng_seed,
        )
        prices_inserted += _insert_prices(session, security_id, bars)

    fundamentals_upserted = _seed_fundamentals(session)
    if prices_inserted > 0:
        queue_version_bump(session, "prices")
    if fundamentals_upserted > 0:
        queue_version_bump(session, "fundamentals")

    logger.info(
        "seed_complete",
        extra={
            "securities": securities_upserted,
            "price_rows_attempted": prices_inserted,
            "fundamentals": fundamentals_upserted,
        },
    )
    return {
        "securities": securities_upserted,
        "prices_inserted": prices_inserted,
        "fundamentals": fundamentals_upserted,
        "demo_user_id": str(demo_user_id),
    }


def _seed_fundamentals(session: Session) -> int:
    written = 0
    for ticker, metrics in FUNDAMENTALS.items():
        security_id = session.execute(
            select(Security.id).where(Security.ticker == ticker)
        ).scalar_one()
        stmt = (
            insert(Fundamental)
            .values(
                security_id=security_id,
                as_of=FUNDAMENTAL_AS_OF,
                roe=Decimal(metrics["roe"]),
                pe_ratio=Decimal(metrics["pe_ratio"]),
                revenue_growth=Decimal(metrics["revenue_growth"]),
                market_cap=Decimal(metrics["market_cap"]),
                provider="seed",
            )
            .on_conflict_do_update(
                index_elements=["security_id"],
                set_={
                    "as_of": FUNDAMENTAL_AS_OF,
                    "roe": Decimal(metrics["roe"]),
                    "pe_ratio": Decimal(metrics["pe_ratio"]),
                    "revenue_growth": Decimal(metrics["revenue_growth"]),
                    "market_cap": Decimal(metrics["market_cap"]),
                    "provider": "seed",
                    "updated_at": func.now(),
                },
            )
        )
        session.execute(stmt)
        written += 1
    return written


def _insert_prices(
    session: Session,
    security_id: UUID,
    bars: list[dict[str, object]],
) -> int:
    if not bars:
        return 0
    inserted = 0
    for offset in range(0, len(bars), INSERT_CHUNK):
        window = bars[offset : offset + INSERT_CHUNK]
        chunk = [{"security_id": security_id, **bar} for bar in window]
        stmt = insert(Price).values(chunk).on_conflict_do_nothing(
            index_elements=["security_id", "timestamp"]
        )
        result = session.execute(stmt)
        inserted += result.rowcount or 0
    return inserted
