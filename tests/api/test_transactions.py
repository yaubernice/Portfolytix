from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.cache import PENDING_BUMPS
from app.db.models import Security, User
from tests.api.helpers import create_portfolio


def test_buy_buy_sell_net_holdings(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    apple: Security,
) -> None:
    portfolio = create_portfolio(client, user.id)
    portfolio_id = portfolio["id"]
    stamp = datetime(2024, 6, 3, 14, 30, tzinfo=UTC).isoformat()

    first = client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": "aapl",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "185.50",
            "timestamp": stamp,
        },
    )
    assert first.status_code == 201
    assert first.json()["ticker"] == "AAPL"
    assert f"portfolio:{portfolio_id}" in sqlite_session.info[PENDING_BUMPS]

    client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": apple.ticker,
            "transaction_type": "BUY",
            "quantity": "5",
            "price": "190",
        },
    )
    client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": apple.ticker,
            "transaction_type": "SELL",
            "quantity": "3",
            "price": "200",
        },
    )

    holdings = client.get(f"/portfolios/{portfolio_id}/holdings")
    assert holdings.status_code == 200
    assert holdings.json() == [
        {
            "security_id": str(apple.id),
            "ticker": apple.ticker,
            "quantity": "12",
        }
    ]

    detail = client.get(f"/portfolios/{portfolio_id}")
    assert detail.json()["holdings"][0]["quantity"] == "12"

    ledger = client.get(f"/portfolios/{portfolio_id}/transactions")
    assert ledger.status_code == 200
    assert len(ledger.json()) == 3


def test_sell_without_shares_is_conflict(
    client: TestClient, user: User, apple: Security
) -> None:
    portfolio = create_portfolio(client, user.id)
    response = client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": apple.ticker,
            "transaction_type": "SELL",
            "quantity": "1",
            "price": "185",
        },
    )
    assert response.status_code == 409
    assert "current position is 0" in response.json()["detail"]


def test_unknown_ticker_is_not_found(client: TestClient, user: User) -> None:
    portfolio = create_portfolio(client, user.id)
    response = client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": "ZZZZ",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "10",
        },
    )
    assert response.status_code == 404


def test_sold_out_position_omitted_from_holdings(
    client: TestClient, user: User, apple: Security
) -> None:
    portfolio = create_portfolio(client, user.id)
    path = f"/portfolios/{portfolio['id']}/transactions"
    client.post(
        path,
        json={
            "ticker": apple.ticker,
            "transaction_type": "BUY",
            "quantity": "4",
            "price": "100",
        },
    )
    client.post(
        path,
        json={
            "ticker": apple.ticker,
            "transaction_type": "SELL",
            "quantity": "4",
            "price": "110",
        },
    )
    holdings = client.get(f"/portfolios/{portfolio['id']}/holdings")
    assert holdings.json() == []


def test_invalid_transaction_body_is_rejected(
    client: TestClient, user: User, apple: Security
) -> None:
    portfolio = create_portfolio(client, user.id)
    path = f"/portfolios/{portfolio['id']}/transactions"
    zero_quantity = client.post(
        path,
        json={
            "ticker": apple.ticker,
            "transaction_type": "BUY",
            "quantity": "0",
            "price": "10",
        },
    )
    bad_type = client.post(
        path,
        json={
            "ticker": apple.ticker,
            "transaction_type": "DIVIDEND",
            "quantity": "1",
            "price": "10",
        },
    )
    assert zero_quantity.status_code == 422
    assert bad_type.status_code == 422


def test_missing_portfolio_reads_are_not_found(client: TestClient) -> None:
    missing = uuid4()
    assert client.get(f"/portfolios/{missing}/transactions").status_code == 404
    assert client.get(f"/portfolios/{missing}/holdings").status_code == 404
