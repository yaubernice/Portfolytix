"""Generate or remove a deterministic PostgreSQL price benchmark dataset.

Default size: 10,000 securities × 1,000 daily bars = 10,000,000 prices.
The SQL is set-based so Python does not allocate ten million ORM objects.

Usage:
    python scripts/generate_benchmark_data.py
    python scripts/generate_benchmark_data.py --securities 100 --days 100
    python scripts/generate_benchmark_data.py --cleanup
"""

from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine

logger = logging.getLogger(__name__)

PREFIX = "BENCH"

INSERT_SECURITIES = """
INSERT INTO securities (
    id, ticker, name, exchange, sector, currency, created_at, updated_at
)
SELECT
    (
        substr(md5('security-' || n::text), 1, 8) || '-' ||
        substr(md5('security-' || n::text), 9, 4) || '-' ||
        substr(md5('security-' || n::text), 13, 4) || '-' ||
        substr(md5('security-' || n::text), 17, 4) || '-' ||
        substr(md5('security-' || n::text), 21, 12)
    )::uuid,
    'BENCH' || lpad(n::text, 11, '0'),
    'Benchmark Security ' || n,
    'BENCH',
    CASE n % 4
        WHEN 0 THEN 'Technology'
        WHEN 1 THEN 'Financials'
        WHEN 2 THEN 'Healthcare'
        ELSE 'Industrials'
    END,
    'USD',
    now(),
    now()
FROM generate_series(1, :securities) AS source(n)
ON CONFLICT (ticker) DO NOTHING
"""

INSERT_PRICES = """
INSERT INTO prices (
    id, security_id, timestamp, open, high, low, close,
    adjusted_close, volume
)
SELECT
    (
        substr(md5(s.id::text || '-' || d::text), 1, 8) || '-' ||
        substr(md5(s.id::text || '-' || d::text), 9, 4) || '-' ||
        substr(md5(s.id::text || '-' || d::text), 13, 4) || '-' ||
        substr(md5(s.id::text || '-' || d::text), 17, 4) || '-' ||
        substr(md5(s.id::text || '-' || d::text), 21, 12)
    )::uuid,
    s.id,
    timestamptz '2010-01-01 00:00:00+00' + d * interval '1 day',
    (100 + (d % 100) * 0.01)::numeric(18, 6),
    (101 + (d % 100) * 0.01)::numeric(18, 6),
    (99 + (d % 100) * 0.01)::numeric(18, 6),
    (100.5 + (d % 100) * 0.01)::numeric(18, 6),
    (100.5 + (d % 100) * 0.01)::numeric(18, 6),
    1000000 + d
FROM securities AS s
CROSS JOIN generate_series(0, :days - 1) AS dates(d)
WHERE s.ticker LIKE 'BENCH%'
ORDER BY s.id, d
ON CONFLICT (security_id, timestamp) DO NOTHING
"""


def main() -> int:
    args = _parse_args()
    setup_logging(settings.log_level)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Phase 8 benchmark generation requires PostgreSQL")

    if args.cleanup:
        with engine.begin() as connection:
            deleted = connection.execute(
                text("DELETE FROM securities WHERE ticker LIKE 'BENCH%'")
            ).rowcount
        print(f"Deleted {deleted or 0} benchmark securities (prices cascaded).")
        return 0

    started = time.perf_counter()
    with engine.begin() as connection:
        connection.execute(
            text(INSERT_SECURITIES),
            {"securities": args.securities},
        )
        connection.execute(
            text(INSERT_PRICES),
            {"days": args.days},
        )
    insert_seconds = time.perf_counter() - started

    # ANALYZE gives the planner current cardinality statistics. VACUUM marks
    # pages all-visible, which is required for a fair index-only-scan test.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM (ANALYZE) prices"))
        security_count = connection.scalar(
            text("SELECT count(*) FROM securities WHERE ticker LIKE 'BENCH%'")
        )
        price_count = connection.scalar(
            text(
                """
                SELECT count(*)
                FROM prices AS p
                JOIN securities AS s ON s.id = p.security_id
                WHERE s.ticker LIKE 'BENCH%'
                """
            )
        )

    print(
        f"Benchmark data ready: {security_count} securities, "
        f"{price_count} prices, insert={insert_seconds:.2f}s."
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--securities", type=int, default=10_000)
    parser.add_argument("--days", type=int, default=1_000)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.securities < 1 or args.days < 1:
        parser.error("--securities and --days must be >= 1")
    if args.securities > 99_999_999_999:
        parser.error("--securities is too large for the 16-character ticker")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
