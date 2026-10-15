from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.models import Fundamental, Price, Security, User
from tests.api.helpers import create_portfolio

EXPECTED = {
    "max-drawdown",
    "volatility",
    "sharpe-ratio",
    "time-weighted-return",
    "unrealized-pl",
    "day-pl",
    "pe-ratio",
    "roe",
}


def _bar(session: Session, security_id, day: datetime, close: str) -> None:
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


def _buy(client: TestClient, portfolio_id: str, day: str) -> None:
    response = client.post(
        f"/portfolios/{portfolio_id}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": day,
        },
    )
    assert response.status_code == 201, response.text


def test_catalog_lists_the_first_metrics(client: TestClient) -> None:
    response = client.get("/learn")
    assert response.status_code == 200, response.text
    slugs = {row["slug"] for row in response.json()["terms"]}
    assert EXPECTED <= slugs


def test_unknown_term_is_not_found(client: TestClient) -> None:
    response = client.get("/learn/not-a-metric")
    assert response.status_code == 404


def test_drawdown_uses_the_calculated_series(
    client: TestClient, sqlite_session: Session, user: User, apple: Security
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    _bar(sqlite_session, apple.id, datetime(2024, 1, 2, tzinfo=UTC), "100")
    _bar(sqlite_session, apple.id, datetime(2024, 1, 3, tzinfo=UTC), "110")
    _bar(sqlite_session, apple.id, datetime(2024, 1, 4, tzinfo=UTC), "99")
    _buy(client, portfolio_id, "2024-01-02T00:00:00Z")

    analytics = client.get(f"/portfolios/{portfolio_id}/analytics")
    assert analytics.status_code == 200, analytics.text
    drawdown = analytics.json()["max_drawdown"]

    page = client.get(
        "/learn/max-drawdown", params={"portfolio_id": portfolio_id}
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert "-10%" in body["meaning"]
    assert "0.1" not in body["meaning"]
    observation = body["observation"]
    assert observation["available"] is True
    facts = {row["label"]: row["value"] for row in observation["facts"]}
    assert facts["Maximum drawdown"] == "-10.0%"
    assert drawdown == "-0.1"
    assert facts["Peak date"] == "2024-01-03"
    assert facts["Trough date"] == "2024-01-04"
    assert "not a permanent loss" in observation["summary"]
    assert "not a forecast" in observation["summary"]
    assert body["portfolio_id"] == portfolio_id


def test_flat_drawdown_does_not_invent_a_decline(
    client: TestClient, sqlite_session: Session, user: User, apple: Security
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    _bar(sqlite_session, apple.id, datetime(2024, 1, 2, tzinfo=UTC), "100")
    _bar(sqlite_session, apple.id, datetime(2024, 1, 3, tzinfo=UTC), "110")
    _buy(client, portfolio_id, "2024-01-02T00:00:00Z")

    page = client.get(
        "/learn/max-drawdown", params={"portfolio_id": portfolio_id}
    )
    assert page.status_code == 200, page.text
    observation = page.json()["observation"]
    assert observation["available"] is True
    assert "did not fall" in observation["summary"]
    assert "-10" not in observation["summary"]
    facts = {row["label"]: row["value"] for row in observation["facts"]}
    assert facts["Maximum drawdown"] == "0.0%"

    sharpe = client.get(
        "/learn/sharpe-ratio", params={"portfolio_id": portfolio_id}
    )
    assert sharpe.status_code == 200, sharpe.text
    blocked = sharpe.json()["observation"]
    assert blocked["available"] is False
    assert "at least two" in blocked["unavailable_reason"]


def test_empty_portfolio_explains_why(client: TestClient, user: User) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    page = client.get(
        "/learn/time-weighted-return", params={"portfolio_id": portfolio_id}
    )
    assert page.status_code == 200, page.text
    observation = page.json()["observation"]
    assert observation["available"] is False
    assert "no transactions" in observation["unavailable_reason"]
    assert "no transactions" not in page.json()["meaning"]


def test_other_user_portfolio_is_hidden(
    client: TestClient, user: User, other_user: User
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    response = client.get(
        "/learn/volatility",
        params={"portfolio_id": portfolio_id},
        headers={"Authorization": f"Bearer {create_access_token(other_user.id)}"},
    )
    assert response.status_code == 404


def test_missing_pe_explains_the_gap(
    client: TestClient, user: User, apple: Security
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    _buy(client, portfolio_id, "2024-01-02T00:00:00Z")
    page = client.get(
        "/learn/pe-ratio",
        params={"portfolio_id": portfolio_id, "ticker": "AAPL"},
    )
    assert page.status_code == 200, page.text
    observation = page.json()["observation"]
    assert observation["available"] is False
    assert "No fundamental snapshot" in observation["unavailable_reason"]
    assert "not a recommendation" in page.json()["limitations"]


def test_stored_pe_is_labeled_as_a_snapshot(
    client: TestClient, sqlite_session: Session, user: User, apple: Security
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    _buy(client, portfolio_id, "2024-01-02T00:00:00Z")
    sqlite_session.add(
        Fundamental(
            security_id=apple.id,
            as_of=date(2024, 1, 1),
            roe=Decimal("0.15"),
            pe_ratio=Decimal("28"),
            revenue_growth=Decimal("0.1"),
            market_cap=Decimal("1000000000"),
        )
    )
    sqlite_session.flush()
    page = client.get(
        "/learn/pe-ratio",
        params={"portfolio_id": portfolio_id, "ticker": apple.ticker},
    )
    assert page.status_code == 200, page.text
    body = page.json()
    facts = {row["label"]: row["value"] for row in body["observation"]["facts"]}
    assert facts["P/E"] == "28.00"
    assert facts["Open position in the selected portfolio"] == "Yes"
    assert "28" not in body["meaning"]
    assert str(uuid4()) not in body["meaning"]


def test_explain_joins_the_formula_to_the_portfolio(
    client: TestClient, sqlite_session: Session, user: User, apple: Security
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    _bar(sqlite_session, apple.id, datetime(2024, 1, 2, tzinfo=UTC), "100")
    _bar(sqlite_session, apple.id, datetime(2024, 1, 3, tzinfo=UTC), "110")
    _bar(sqlite_session, apple.id, datetime(2024, 1, 4, tzinfo=UTC), "99")
    _buy(client, portfolio_id, "2024-01-02T00:00:00Z")

    response = client.post(
        "/learn/explain",
        json={"text": "Max drawdown", "portfolio_id": portfolio_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "glossary"
    assert "MDD" in body["formula"]
    assert len(body["what"]) < 80
    assert "−10%" in body["example"] or "-10%" in body["example"]
    assert "-10.0%" in body["yours"]
    assert "forecast" in body["watch"].lower()


def test_unknown_phrase_is_not_a_fixed_lesson(
    client: TestClient, user: User
) -> None:
    portfolio_id = create_portfolio(client, user.id)["id"]
    response = client.post(
        "/learn/explain",
        json={"text": "accrued interest", "portfolio_id": portfolio_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "template"
    assert body["formula"] == ""
    assert "accrued interest" in body["what"]
    assert len(body["what"]) < 120
    assert "-10.0%" not in body["yours"]
    assert "forecast" in body["watch"].lower()
