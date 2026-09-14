"""Load reference securities and synthetic daily prices.

Usage (Postgres must be up and migrated):

    python scripts/seed_database.py
    # or: make seed-host
    # or: make seed   (inside the api container)
"""

from __future__ import annotations

import sys

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.seed import seed_market_data
from app.db.session import SessionLocal


def main() -> int:
    setup_logging(settings.log_level)
    session = SessionLocal()
    try:
        result = seed_market_data(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        "Seed complete: "
        f"{result['securities']} securities upserted, "
        f"{result['prices_inserted']} new price rows, "
        f"demo user {result['demo_user_id']}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
