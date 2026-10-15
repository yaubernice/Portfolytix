"""Load US exchange listings into ``securities``.

The Nasdaq Trader symbol directory is a public file, not a priced feed.
Existing tickers are left unchanged, including seeded fundamentals.
``BENCH`` placeholder rows are marked inactive.

    python scripts/sync_listings.py
"""

from __future__ import annotations

import sys

import httpx

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.market_data.errors import ProviderError
from app.market_data.listings import (
    NASDAQ_LISTED_URL,
    OTHER_LISTED_URL,
    apply_listings,
    merge_listings,
    parse_nasdaq_listed,
    parse_other_listed,
)


def main() -> int:
    setup_logging("INFO")
    try:
        nasdaq = _download(NASDAQ_LISTED_URL)
        other = _download(OTHER_LISTED_URL)
        listings = merge_listings(
            parse_nasdaq_listed(nasdaq),
            parse_other_listed(other),
        )
    except (ProviderError, httpx.HTTPError) as exc:
        print(f"Listing download failed: {exc}", file=sys.stderr)
        return 1
    session = SessionLocal()
    try:
        added, retired = apply_listings(session, listings)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(
        f"Parsed {len(listings)} US listings. "
        f"Inserted {added}. Retired {retired} BENCH rows."
    )
    return 0


def _download(url: str) -> str:
    response = httpx.get(
        url,
        timeout=60.0,
        headers={"User-Agent": "FinSight/1.0"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


if __name__ == "__main__":
    raise SystemExit(main())
