from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_quote_store
from app.core.security import create_access_token
from app.db.models import Fundamental, Price, Security, User
from app.main import app
from app.quotes.store import MemoryQuoteStore
from tests.api.helpers import create_portfolio


def _security(session: Session, ticker: str, sector: str) -> Security:
    row = Security(
        ticker=ticker,
        name=f"{ticker} Inc.",
        exchange="NASDAQ",
        sector=sector,
        currency="USD",
    )
    session.add(row)
    session.flush()
    return row


def _fundamental(session: Session, security: Security, roe: str) -> None:
    session.add(
        Fundamental(
            security_id=security.id,
            as_of=date(2026, 1, 1),
            roe=Decimal(roe),
            pe_ratio=Decimal("20"),
            revenue_growth=Decimal("0.10"),
            market_cap=Decimal("1000000000"),
        )
    )


def test_recommendations_prefer_a_sector_the_portfolio_does_not_hold(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    other_user: User,
    apple: Security,
) -> None:
    microsoft = _security(sqlite_session, "MSFT", "Technology")
    google = _security(sqlite_session, "GOOGL", "Communication Services")
    _fundamental(sqlite_session, apple, "0.20")
    _fundamental(sqlite_session, microsoft, "0.40")
    _fundamental(sqlite_session, google, "0.10")
    sqlite_session.commit()
    portfolio = create_portfolio(client, user.id)
    bought = client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    assert bought.status_code == 201, bought.text

    response = client.get(f"/portfolios/{portfolio['id']}/recommendations")
    assert response.status_code == 200, response.text
    tickers = [row["ticker"] for row in response.json()["items"]]
    assert tickers[0] == "GOOGL"
    assert "MSFT" in tickers
    assert "AAPL" not in tickers
    reason = response.json()["items"][0]["reason"]
    assert "No open position is in Communication Services." in reason
    assert "not investment advice" in response.json()["disclaimer"]

    hidden = client.get(
        f"/portfolios/{portfolio['id']}/recommendations",
        headers={"Authorization": f"Bearer {create_access_token(other_user.id)}"},
    )
    assert hidden.status_code == 404


def test_attention_lists_a_down_day_and_flags_stay_with_the_owner(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    other_user: User,
    apple: Security,
) -> None:
    for day, close in (
        (datetime(2024, 1, 2, tzinfo=UTC), "110"),
        (datetime(2024, 1, 3, tzinfo=UTC), "100"),
    ):
        price = Decimal(close)
        sqlite_session.add(
            Price(
                security_id=apple.id,
                timestamp=day,
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=price,
                volume=1,
            )
        )
    sqlite_session.commit()
    app.dependency_overrides[get_quote_store] = lambda: MemoryQuoteStore()
    portfolio = create_portfolio(client, user.id)
    client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    attention = client.get(f"/portfolios/{portfolio['id']}/attention")
    assert attention.status_code == 200, attention.text
    body = attention.json()
    assert body["stocks"][0]["ticker"] == "AAPL"
    assert Decimal(body["stocks"][0]["day_pl"]) < 0
    assert body["areas"][0]["sector"] == "Technology"

    missing = client.post(
        "/flags",
        json={"target_type": "security", "security_id": str(uuid4())},
    )
    assert missing.status_code == 404

    created = client.post(
        "/flags",
        json={
            "target_type": "security",
            "security_id": str(apple.id),
            "note": "Negative day move",
        },
    )
    assert created.status_code == 201, created.text
    flag_id = created.json()["id"]
    assert created.json()["ticker"] == "AAPL"

    again = client.post(
        "/flags",
        json={"target_type": "security", "security_id": str(apple.id)},
    )
    assert again.status_code == 409

    sector = client.post(
        "/flags",
        json={"target_type": "sector", "sector": "technology"},
    )
    assert sector.status_code == 201, sector.text
    assert sector.json()["sector"] == "Technology"

    listed = client.get("/flags")
    assert listed.status_code == 200
    assert {row["id"] for row in listed.json()} >= {flag_id, sector.json()["id"]}

    other = client.get(
        "/flags",
        headers={"Authorization": f"Bearer {create_access_token(other_user.id)}"},
    )
    assert other.status_code == 200
    assert other.json() == []
    stolen = client.delete(
        f"/flags/{flag_id}",
        headers={"Authorization": f"Bearer {create_access_token(other_user.id)}"},
    )
    assert stolen.status_code == 404

    removed = client.delete(f"/flags/{flag_id}")
    assert removed.status_code == 204
