from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Price, Security, User
from tests.api.helpers import create_portfolio


def _bar(
    session: Session,
    security_id: UUID,
    day: datetime,
    close: str,
) -> None:
    price = Decimal(close)
    session.add(
        Price(
            security_id=security_id,
            timestamp=day,
            open=price,
            high=price,
            low=price,
            close=price,
            adjusted_close=price,
            volume=1,
        )
    )
    session.flush()


def test_analytics_twr_and_allocation(
    client: TestClient, sqlite_session: Session, user: User, apple: Security
) -> None:
    portfolio = create_portfolio(client, user.id)
    portfolio_id = portfolio["id"]
    _bar(sqlite_session, apple.id, datetime(2024, 1, 2, tzinfo=UTC), "100")
    _bar(sqlite_session, apple.id, datetime(2024, 1, 3, tzinfo=UTC), "110")

    buy = client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    assert buy.status_code == 201, buy.text

    response = client.get(f"/portfolios/{portfolio_id}/analytics")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_return"] == "0.1"
    assert body["max_drawdown"] == "0"
    assert body["observation_count"] == 1
    assert body["allocation"][0]["ticker"] == "AAPL"
    assert body["allocation"][0]["weight"] == "1"
    assert body["assumptions"]["method"] == "time_weighted"
    assert "Not investment advice" in body["assumptions"]["disclaimer"]
    assert body["series"][-1]["daily_return"] == "0.1"


def test_analytics_requires_transactions_and_prices(
    client: TestClient, sqlite_session: Session, user: User, apple: Security
) -> None:
    portfolio = create_portfolio(client, user.id)
    portfolio_id = portfolio["id"]

    empty = client.get(f"/portfolios/{portfolio_id}/analytics")
    assert empty.status_code == 409

    client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    no_prices = client.get(f"/portfolios/{portfolio_id}/analytics")
    assert no_prices.status_code == 409


def test_analytics_unknown_portfolio(client: TestClient) -> None:
    response = client.get(f"/portfolios/{uuid4()}/analytics")
    assert response.status_code == 404
