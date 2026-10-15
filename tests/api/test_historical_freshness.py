from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Price, Security
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar
from app.services.market_data_service import MarketDataService


class _OneBar(MarketDataProvider):
    name = "fixture"

    def fetch_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> list[RawBar]:
        close = Decimal("100")
        return [
            RawBar(
                ticker=ticker,
                day=start,
                open=close,
                high=close,
                low=close,
                close=close,
                adjusted_close=close,
                volume=1,
            )
        ]


def test_missing_history_is_filled_only_when_asked(
    client: TestClient,
    apple: Security,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.reference_service.YahooHistoryProvider",
        lambda: _OneBar(),
    )
    skipped = client.get("/securities/AAPL")
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["latest_close"] is None

    filled = client.get("/securities/AAPL", params={"ensure_history": True})
    assert filled.status_code == 200, filled.text
    body = filled.json()
    assert body["latest_close"] == "100"
    assert body["history_source"] == "fixture"
    assert body["live_timeliness"] == "unavailable"
    assert body["prices"]


def test_freshness_describes_the_stored_bar(
    client: TestClient,
    sqlite_session: Session,
    apple: Security,
) -> None:
    day = date(2024, 1, 2)
    MarketDataService(sqlite_session, _OneBar()).ingest(["AAPL"], day, day)
    sqlite_session.commit()

    missing = client.get("/securities/MSFT/freshness")
    assert missing.status_code == 404

    response = client.get("/securities/AAPL/freshness")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["latest_bar"] == "2024-01-02"
    assert body["source"] == "fixture"
    assert body["timeliness"] == "historical"
    assert body["is_stale"] is True
    assert body["last_successful_update"] is not None

    profile = client.get("/securities/AAPL")
    assert profile.status_code == 200, profile.text
    assert profile.json()["history_timeliness"] == "historical"
    assert profile.json()["history_is_stale"] is True
    assert profile.json()["history_source"] == "fixture"


def test_profile_history_period_and_limit(
    client: TestClient,
    sqlite_session: Session,
    apple: Security,
) -> None:
    latest = datetime(2026, 10, 14, tzinfo=UTC)
    for days_ago in (0, 3, 10, 40, 400):
        value = Decimal(100 + days_ago)
        sqlite_session.add(
            Price(
                security_id=apple.id,
                timestamp=latest - timedelta(days=days_ago),
                open=value,
                high=value,
                low=value,
                close=value,
                adjusted_close=value,
                volume=days_ago + 1,
                source="fixture",
                ingested_at=latest,
            )
        )
    sqlite_session.commit()

    week = client.get("/securities/AAPL?period=1W&history_limit=10")
    assert week.status_code == 200, week.text
    assert [bar["date"] for bar in week.json()["prices"]] == [
        "2026-10-11",
        "2026-10-14",
    ]

    maximum = client.get("/securities/AAPL?period=MAX&history_limit=3")
    assert maximum.status_code == 200, maximum.text
    assert len(maximum.json()["prices"]) == 3
    assert maximum.json()["prices"][-1]["date"] == "2026-10-14"

    invalid = client.get("/securities/AAPL?period=5Y")
    assert invalid.status_code == 422
