from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_quote_store
from app.db.models import Price, Security, User
from app.main import app
from app.quotes.models import quote_from_parts
from app.quotes.store import MemoryQuoteStore
from tests.api.helpers import create_portfolio


def test_quotes_require_a_valid_token(client: TestClient) -> None:
    response = client.get("/quotes", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_quote_snapshot_comes_from_the_store(client: TestClient) -> None:
    store = MemoryQuoteStore()
    store.publish(
        quote_from_parts(
            ticker="AAPL",
            price=Decimal("190"),
            previous_close=Decimal("185"),
            timestamp=datetime(2026, 10, 3, tzinfo=UTC),
            source="simulator",
        )
    )
    app.dependency_overrides[get_quote_store] = lambda: store
    response = client.get("/quotes")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quotes"][0]["ticker"] == "AAPL"
    assert body["quotes"][0]["price"] == "190"
    assert Decimal(body["quotes"][0]["change"]) == Decimal("5")


def test_quote_snapshot_filters_multiple_symbols_and_rejects_invalid_input(
    client: TestClient,
) -> None:
    store = MemoryQuoteStore()
    for ticker, price in (("AAPL", "190"), ("MSFT", "420"), ("NVDA", "150")):
        store.publish(
            quote_from_parts(
                ticker=ticker,
                price=Decimal(price),
                timestamp=datetime.now(UTC),
                source="test",
            )
        )
    app.dependency_overrides[get_quote_store] = lambda: store
    response = client.get("/quotes", params={"tickers": "msft, AAPL,msft"})
    assert response.status_code == 200
    assert [row["ticker"] for row in response.json()["quotes"]] == ["AAPL", "MSFT"]
    invalid = client.get("/quotes", params={"tickers": "AAPL;DROP TABLE"})
    assert invalid.status_code == 422


def test_positions_use_average_cost_and_last_close(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    apple: Security,
) -> None:
    portfolio = create_portfolio(client, user.id)
    for day, close in (
        (datetime(2024, 1, 2, tzinfo=UTC), "100"),
        (datetime(2024, 1, 3, tzinfo=UTC), "110"),
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
    bought = client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "4",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    assert bought.status_code == 201, bought.text
    response = client.get(f"/portfolios/{portfolio['id']}/positions")
    assert response.status_code == 200, response.text
    body = response.json()
    row = body["positions"][0]
    assert row["ticker"] == "AAPL"
    assert row["quantity"] == "4"
    assert row["average_cost"] == "100"
    assert row["avg_cost"] == "100"
    assert row["cost_basis"] == "400"
    assert row["current_price"] == "110"
    assert row["price"] == "110"
    assert row["price_source"] == "database"
    assert row["freshness"]["source"] == "database"
    assert row["freshness"]["timeliness"] == "historical"
    assert row["unrealized_pl"] == "40"
    assert row["day_pl"] == "40"
    assert row["weight"] == "1"
    assert body["cost_basis"] == "400"
    assert body["market_value"] == "440"
    assert body["unrealized_pl"] == "40"
    assert body["day_pl"] == "40"
    assert body["top_contributors"][0]["ticker"] == "AAPL"
    assert body["top_contributors"][0]["day_pl"] == "40"
    assert body["top_detractors"] == []


def test_positions_rank_day_pl_contributors_and_detractors(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    apple: Security,
) -> None:
    microsoft = Security(
        ticker="MSFT",
        name="Microsoft",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    sqlite_session.add(microsoft)
    sqlite_session.flush()
    portfolio = create_portfolio(client, user.id)
    for security, closes in ((apple, ("100", "110")), (microsoft, ("100", "90"))):
        for day, close in zip((2, 3), closes, strict=True):
            price = Decimal(close)
            sqlite_session.add(
                Price(
                    security_id=security.id,
                    timestamp=datetime(2024, 1, day, tzinfo=UTC),
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    adjusted_close=price,
                    volume=1,
                )
            )
    sqlite_session.commit()
    for ticker, quantity in (("AAPL", "1"), ("MSFT", "2")):
        response = client.post(
            f"/portfolios/{portfolio['id']}/transactions",
            json={
                "ticker": ticker,
                "transaction_type": "BUY",
                "quantity": quantity,
                "price": "100",
                "timestamp": "2024-01-02T00:00:00Z",
            },
        )
        assert response.status_code == 201, response.text

    body = client.get(f"/portfolios/{portfolio['id']}/positions").json()

    assert body["top_contributors"][0]["ticker"] == "AAPL"
    assert body["top_contributors"][0]["day_pl"] == "10"
    assert body["top_detractors"][0]["ticker"] == "MSFT"
    assert body["top_detractors"][0]["day_pl"] == "-20"


def test_websocket_relays_a_published_quote(client: TestClient, user: User) -> None:
    from app.core.security import create_access_token

    store = MemoryQuoteStore()
    app.dependency_overrides[get_quote_store] = lambda: store
    token = create_access_token(user.id)
    with client.websocket_connect(f"/ws/quotes?token={token}") as socket:
        snapshot = socket.receive_json()
        assert snapshot == {"type": "snapshot", "quotes": []}
        store.publish(
            quote_from_parts(
                ticker="NVDA",
                price=Decimal("190"),
                previous_close=Decimal("180"),
                timestamp=datetime(2026, 10, 3, tzinfo=UTC),
                source="simulator",
            )
        )
        message = socket.receive_json()
    assert message["type"] == "quote"
    assert message["quote"]["ticker"] == "NVDA"
