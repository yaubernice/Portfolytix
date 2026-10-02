from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Fundamental, Security


def _row(
    session: Session,
    ticker: str,
    *,
    sector: str,
    roe: str,
    pe: str,
    growth: str,
    mcap: str,
) -> None:
    security = Security(
        ticker=ticker,
        name=f"{ticker} Inc.",
        exchange="NASDAQ",
        sector=sector,
        currency="USD",
    )
    session.add(security)
    session.flush()
    session.add(
        Fundamental(
            security_id=security.id,
            as_of=date(2025, 12, 31),
            roe=Decimal(roe),
            pe_ratio=Decimal(pe),
            revenue_growth=Decimal(growth),
            market_cap=Decimal(mcap),
        )
    )
    session.flush()


def _seed(session: Session) -> None:
    _row(
        session, "GOOGL", sector="Communication Services",
        roe="0.28", pe="22", growth="0.12", mcap="2000000000000",
    )
    _row(
        session, "META", sector="Communication Services",
        roe="0.32", pe="24", growth="0.16", mcap="1200000000000",
    )
    _row(
        session, "AAPL", sector="Technology",
        roe="0.35", pe="28", growth="0.08", mcap="3500000000000",
    )


def test_post_screen_example_filter(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    _seed(sqlite_session)
    response = client.post(
        "/screen",
        json={
            "roe_min": "0.15",
            "pe_max": "30",
            "revenue_growth_min": "0.10",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [hit["ticker"] for hit in body["items"]] == ["GOOGL", "META"]
    assert body["items"][0]["roe"] == "0.28"
    assert body["applied"]["pe_max"] == "30"


def test_post_screen_pagination(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    _seed(sqlite_session)
    response = client.post(
        "/screen",
        json={
            "roe_min": "0.15",
            "pe_max": "30",
            "revenue_growth_min": "0.10",
            "limit": 1,
            "offset": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert body["items"][0]["ticker"] == "META"


def test_post_screen_rejects_unknown_field(client: TestClient) -> None:
    response = client.post("/screen", json={"sql": "DROP TABLE securities"})
    assert response.status_code == 422


def test_post_screen_rejects_bad_range(client: TestClient) -> None:
    response = client.post(
        "/screen",
        json={"market_cap_min": "20", "market_cap_max": "10"},
    )
    assert response.status_code == 422
