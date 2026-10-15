"""Fetch daily bars from the configured provider and upsert into Postgres.

Usage (Postgres must be up; securities must already exist from seed):

    python scripts/ingest_market_data.py
    python scripts/ingest_market_data.py --ticker AAPL --start 2024-01-02
    python scripts/ingest_market_data.py --provider stooq

Never pass API keys on the command line; use MARKET_DATA_API_KEY.
Records a row in ``job_runs`` (same path the scheduler uses).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from app.core.cache import commit_and_invalidate, get_cache
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.models import JobStatus
from app.db.session import SessionLocal
from app.jobs.market_data_job import DEFAULT_TICKERS, update_market_data
from app.market_data.factory import build_provider


def main(argv: list[str] | None = None) -> int:
    setup_logging(settings.log_level)
    args = _parse(argv)
    provider = build_provider(args.provider)
    session = SessionLocal()
    try:
        tickers = args.tickers
        if tickers is None and not args.exchange and not args.country:
            tickers = DEFAULT_TICKERS
        run = update_market_data(
            session,
            tickers=tickers,
            exchange=args.exchange,
            country=args.country,
            start=args.start,
            end=args.end,
            provider=provider,
            trigger="cli",
        )
        commit_and_invalidate(session, get_cache())
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    _print_run(run)
    return 0 if run.status == JobStatus.SUCCESS else 1


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticker",
        dest="tickers",
        action="append",
        help="Ticker to ingest (repeatable). Default: the seven demo tickers.",
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help="Ingest active securities on this exchange, up to the configured cap.",
    )
    parser.add_argument(
        "--country",
        default=None,
        help="Ingest active securities in this country, up to the configured cap.",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--provider",
        default=None,
        help="alpha_vantage or stooq (default: MARKET_DATA_PROVIDER)",
    )
    return parser.parse_args(argv)


def _print_run(run) -> None:
    print(
        f"job_run {run.id} {run.status} via {run.provider} "
        f"{run.window_start} → {run.window_end}"
    )
    if run.error:
        print(f"  error={run.error}")
    print(
        f"  fetched={run.fetched} accepted={run.accepted} "
        f"upserted={run.upserted} dropped={run.skipped_invalid} "
        f"requested={run.symbols_requested} omitted={run.symbols_omitted}"
    )
    if run.failed_tickers:
        print(f"  failed_tickers={','.join(run.failed_tickers)}")


if __name__ == "__main__":
    sys.exit(main())
