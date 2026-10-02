from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Price
from app.market_data.types import NormalizedBar

INSERT_CHUNK = 500


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_closes(
        self, security_ids: list[UUID]
    ) -> list[tuple[UUID, datetime, Decimal]]:
        if not security_ids:
            return []
        statement = (
            select(Price.security_id, Price.timestamp, Price.adjusted_close)
            .where(Price.security_id.in_(security_ids))
            .order_by(Price.security_id, Price.timestamp)
        )
        return list(self.session.execute(statement).all())

    def count_for_security(self, security_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Price)
            .where(Price.security_id == security_id)
        )
        return int(self.session.scalar(statement) or 0)

    def upsert_bars(
        self,
        security_id: UUID,
        bars: list[NormalizedBar],
    ) -> int:
        """Insert or update bars. Unique (security_id, timestamp) is the key.

        Re-running ingest cannot create duplicates. A later fetch overwrites
        OHLCV so vendor revisions replace the seed random walk.
        """
        if not bars:
            return 0
        insert = _dialect_insert(self.session)
        written = 0
        for offset in range(0, len(bars), INSERT_CHUNK):
            window = bars[offset : offset + INSERT_CHUNK]
            payload = [
                {
                    "id": uuid4(),
                    "security_id": security_id,
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "adjusted_close": bar.adjusted_close,
                    "volume": bar.volume,
                }
                for bar in window
            ]
            stmt = insert(Price).values(payload)
            stmt = stmt.on_conflict_do_update(
                index_elements=["security_id", "timestamp"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "adjusted_close": stmt.excluded.adjusted_close,
                    "volume": stmt.excluded.volume,
                },
            )
            result = self.session.execute(stmt)
            written += result.rowcount or 0
        return written


def _dialect_insert(session: Session):
    name = session.get_bind().dialect.name
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert
    if name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert
    raise RuntimeError(f"Unsupported dialect for price upsert: {name}")

