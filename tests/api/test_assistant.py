from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_quote_store
from app.core.security import create_access_token
from app.db.models import Fundamental, Price, Security, User
from app.main import app
from app.quotes.models import quote_from_parts
from app.quotes.store import MemoryQuoteStore
from tests.api.helpers import create_portfolio


def test_ask_separates_facts_metrics_and_interpretation(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    apple: Security,
) -> None:
    portfolio = create_portfolio(client, user.id)
    portfolio_id = portfolio["id"]
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
    sqlite_session.flush()
    bought = client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    assert bought.status_code == 201, bought.text

    response = client.post(
        f"/portfolios/{portfolio_id}/ask",
        json={"question": "Why did my portfolio volatility increase this month?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    metrics = {item["name"]: item for item in body["metrics"]}
    facts = {item["name"]: item for item in body["facts"]}
    assert metrics["total_return"]["value"] == "0.1"
    assert metrics["total_return"]["source"] == "calculation"
    assert metrics["volatility_change"]["value"] == "insufficient_history"
    assert facts["position:AAPL"]["source"] == "database"
    assert "AAPL" in facts["position:AAPL"]["value"]
    assert body["interpretation_source"] == "template"
    assert "not enough daily returns" in body["interpretation"]
    assert "above the prior window" not in body["interpretation"]
    assert "Not investment advice" in body["disclaimer"]

    streamed = client.post(
        f"/portfolios/{portfolio_id}/ask/stream",
        json={"question": "Summarize this portfolio."},
    )
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    events = streamed.text
    assert events.index("event: evidence") < events.index("event: text")
    assert events.index("event: text") < events.index("event: done")
    assert '"portfolio_id"' in events


def test_other_user_cannot_ask_about_a_portfolio(
    client: TestClient,
    user: User,
    other_user: User,
) -> None:
    portfolio = create_portfolio(client, user.id)
    response = client.post(
        f"/portfolios/{portfolio['id']}/ask",
        json={"question": "What is my volatility?"},
        headers={
            "Authorization": f"Bearer {create_access_token(other_user.id)}",
        },
    )
    assert response.status_code == 404
    streamed = client.post(
        f"/portfolios/{portfolio['id']}/ask/stream",
        json={"question": "What is my volatility?"},
        headers={
            "Authorization": f"Bearer {create_access_token(other_user.id)}",
        },
    )
    assert streamed.status_code == 404


def test_ask_without_transactions_is_conflict(
    client: TestClient,
    user: User,
) -> None:
    portfolio = create_portfolio(client, user.id)
    response = client.post(
        f"/portfolios/{portfolio['id']}/ask",
        json={"question": "Why did volatility increase?"},
    )
    assert response.status_code == 409


def test_natural_screen_runs_the_structured_filter(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    _security(sqlite_session, "MSFT", "Technology", "0.20", "25", "0.12")
    _security(sqlite_session, "AAPL", "Technology", "0.35", "28", "0.08")
    _security(
        sqlite_session,
        "GOOGL",
        "Communication Services",
        "0.28",
        "22",
        "0.12",
    )
    response = client.post(
        "/screen/natural",
        json={
            "query": (
                "Find technology companies with ROE above 15%, "
                "P/E below 30, revenue growth above 10%"
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parser"] == "rules"
    assert [hit["ticker"] for hit in body["items"]] == ["MSFT"]
    assert body["applied"]["sector"] == "technology"
    assert body["applied"]["roe_min"] == "0.15"
    assert body["applied"]["pe_max"] == "30"
    assert body["applied"]["revenue_growth_min"] == "0.1"
    assert body["applied"]["sort_by"] == "ticker"
    assert body["applied"]["sort_direction"] == "asc"


def test_natural_screen_rejects_sql_and_unknown_fields(
    client: TestClient,
) -> None:
    prose = client.post("/screen/natural", json={"query": "OR 1=1"})
    assert prose.status_code == 422
    extra = client.post(
        "/screen/natural",
        json={"query": "technology ROE above 15%", "sql": "select 1"},
    )
    assert extra.status_code == 422


def test_authenticated_safe_tool_endpoint_executes_allowlist(
    client: TestClient,
) -> None:
    store = MemoryQuoteStore()
    store.publish(
        quote_from_parts(
            ticker="AAPL",
            price=Decimal("190"),
            timestamp=datetime(2026, 10, 14, tzinfo=UTC),
            source="test",
        )
    )
    app.dependency_overrides[get_quote_store] = lambda: store
    response = client.post(
        "/assistant/tools/execute",
        json={"name": "current_quote", "ticker": "aapl"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ticker"] == "AAPL"
    assert response.json()["price"] == "190"


def test_safe_tool_endpoint_rejects_database_fields_and_requires_auth(
    client: TestClient,
) -> None:
    for field in ("sql", "query", "raw_sql", "database_query"):
        response = client.post(
            "/assistant/tools/execute",
            json={
                "name": "current_quote",
                "ticker": "AAPL",
                field: "select 1",
            },
        )
        assert response.status_code == 422
    unknown = client.post(
        "/assistant/tools/execute",
        json={"name": "unknown", "ticker": "AAPL"},
    )
    assert unknown.status_code == 422
    unauthorized = client.post(
        "/assistant/tools/execute",
        json={"name": "current_quote", "ticker": "AAPL"},
        headers={"Authorization": "Bearer not-a-token"},
    )
    assert unauthorized.status_code == 401


def _security(
    session: Session,
    ticker: str,
    sector: str,
    roe: str,
    pe: str,
    growth: str,
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
            market_cap=Decimal("1000000000000"),
        )
    )
    session.flush()
