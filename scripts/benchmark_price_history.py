"""Measure price-history query plans with PostgreSQL EXPLAIN ANALYZE.

Run against the same dataset before and after the Phase 8 migration:

    alembic downgrade 0004_phase7_fundamentals
    python scripts/benchmark_price_history.py --label baseline
    alembic upgrade head
    python scripts/benchmark_price_history.py --label optimized

Results are JSON so benchmark claims can be reviewed instead of copied
from a terminal screenshot.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.db.session import engine
from app.performance.benchmark import parse_explain, percent_change, summarize

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "benchmarks" / "results"

PROJECTED_HISTORY_SQL = """
SELECT p.security_id, p.timestamp, p.adjusted_close
FROM prices AS p
WHERE p.security_id IN (
    SELECT id
    FROM securities
    WHERE ticker LIKE 'BENCH%'
    ORDER BY ticker
    LIMIT :security_count
)
AND p.timestamp >= timestamptz '2010-01-01 00:00:00+00'
AND p.timestamp < (
    timestamptz '2010-01-01 00:00:00+00' +
    :days * interval '1 day'
)
ORDER BY p.security_id, p.timestamp
"""

WIDE_HISTORY_SQL = """
SELECT p.*
FROM prices AS p
WHERE p.security_id IN (
    SELECT id
    FROM securities
    WHERE ticker LIKE 'BENCH%'
    ORDER BY ticker
    LIMIT :security_count
)
AND p.timestamp >= timestamptz '2010-01-01 00:00:00+00'
AND p.timestamp < (
    timestamptz '2010-01-01 00:00:00+00' +
    :days * interval '1 day'
)
ORDER BY p.security_id, p.timestamp
"""

EXPLAIN_PREFIX = (
    "EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, SUMMARY, FORMAT JSON) "
)


def main() -> int:
    args = _parse_args()
    if engine.dialect.name != "postgresql": #make sure the database is PostgreSQL
        raise RuntimeError("Phase 8 query benchmarks require PostgreSQL")

    params = {"security_count": args.securities, "days": args.days}
    #set up the parameters for the query
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        # Count every row in prices.
        total_prices = int(
            connection.scalar(text("SELECT count(*) FROM prices")) or 0
        )
        # Count rows that match the benchmark criteria.
        benchmark_prices = int(
            connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM prices AS p
                    JOIN securities AS s ON s.id = p.security_id
                    WHERE s.ticker LIKE 'BENCH%'
                    """
                )
            )
            or 0
        )
        if benchmark_prices == 0: #if there are no benchmark rows, raise an error
            raise RuntimeError(
                "No benchmark rows. Run scripts/generate_benchmark_data.py first."
            )

        connection.execute(text("VACUUM (ANALYZE) prices"))
        # One unrecorded run warms PostgreSQL and the OS page cache.
        # Explain the projected history query.
        _explain(connection, PROJECTED_HISTORY_SQL, params)
        projected = [
            _explain(connection, PROJECTED_HISTORY_SQL, params)
            for _ in range(args.runs)
        ]
        _explain(connection, WIDE_HISTORY_SQL, params)
        wide = [
            _explain(connection, WIDE_HISTORY_SQL, params)
            for _ in range(args.runs)
        ]
        index_definition = connection.scalar(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'prices'
                  AND indexname = 'uq_prices_security_id_timestamp'
                """
            )
        )
        database_version = connection.scalar(text("SELECT version()"))

    projected_summary = summarize(projected)
    wide_summary = summarize(wide)
    result = {
        "label": args.label,
        "recorded_at": datetime.now(UTC).isoformat(),
        "database_version": database_version,
        "index_definition": index_definition,
        "dataset": {
            "total_price_rows": total_prices,
            "benchmark_price_rows": benchmark_prices,
        },
        "query": {
            "securities": args.securities,
            "days": args.days,
            "expected_rows": args.securities * args.days,
            "warmup_runs": 1,
            "measured_runs": args.runs,
        },
        "projected_history": projected_summary.to_dict(),
        "wide_history": wide_summary.to_dict(),
        "projection_execution_change_percent": percent_change(
            wide_summary.execution_ms_median,
            projected_summary.execution_ms_median,
        ),
    }
    output = args.output or RESULTS_DIR / f"{args.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote measured plans to {output}")
    print(
        "projected median="
        f"{projected_summary.execution_ms_median:.3f}ms, "
        f"nodes={', '.join(projected_summary.nodes)}"
    )
    print(
        f"wide median={wide_summary.execution_ms_median:.3f}ms, "
        f"nodes={', '.join(wide_summary.nodes)}"
    )
    return 0


def _explain(connection, sql: str, params: dict[str, int]):
    payload = connection.scalar(text(EXPLAIN_PREFIX + sql), params)
    return parse_explain(payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--securities", type=int, default=1_000)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.securities < 1 or args.days < 1 or args.runs < 1:
        parser.error("--securities, --days, and --runs must be >= 1")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
