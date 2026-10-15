from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Price, Security
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar
from app.services.market_data_service import MarketDataService


class _Bars(MarketDataProvider):
    name = "fake"

    def __init__(self, bars: list[RawBar]) -> None:
        self.bars = bars

    def fetch_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> list[RawBar]:
        return [
            bar
            for bar in self.bars
            if bar.ticker == ticker and start <= bar.day <= end
        ]


def _bar(day: date, close: str) -> RawBar:
    close_d = Decimal(close)
    return RawBar(
        ticker="P11B",
        day=day,
        open=close_d,
        high=close_d + Decimal("1"),
        low=close_d - Decimal("1"),
        close=close_d,
        adjusted_close=close_d,
        volume=100,
    )


def test_postgres_ingest_updates_the_same_daily_bar(
    postgres_session: Session,
) -> None:
    security = Security(
        ticker="P11B",
        name="Phase 11 Bar",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    postgres_session.add(security)
    postgres_session.flush()
    day = date(2024, 1, 2)

    MarketDataService(postgres_session, _Bars([_bar(day, "100.125")])).ingest(
        ["p11b"], day, day
    )
    MarketDataService(postgres_session, _Bars([_bar(day, "101.5")])).ingest(
        ["P11B"], day, day
    )
    postgres_session.flush()

    count = postgres_session.scalar(
        select(func.count())
        .select_from(Price)
        .where(Price.security_id == security.id)
    )
    stored = postgres_session.scalar(
        select(Price).where(Price.security_id == security.id)
    )
    assert count == 1
    assert stored is not None
    assert stored.close == Decimal("101.500000")
    assert stored.adjusted_close == Decimal("101.500000")
    assert isinstance(stored.close, Decimal)
