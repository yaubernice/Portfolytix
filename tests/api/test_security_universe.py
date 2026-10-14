from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Security


def test_security_search_requires_a_token(client: TestClient) -> None:
    response = client.get(
        "/securities/search",
        headers={"Authorization": "Bearer not-a-token"},
    )
    assert response.status_code == 401


def test_search_lists_and_loads_by_id(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    apple = Security(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        country="US",
        currency="USD",
        provider="seed",
        provider_symbol="AAPL",
    )
    bank = Security(
        ticker="HSBA",
        name="HSBC Holdings",
        exchange="LSE",
        sector="Financials",
        country="GB",
        currency="GBP",
        asset_type="equity",
        provider="seed",
        provider_symbol="HSBA.L",
    )
    sqlite_session.add_all([apple, bank])
    sqlite_session.commit()

    found = client.get("/securities/search", params={"q": "hsbc", "country": "GB"})
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["total"] == 1
    assert body["items"][0]["ticker"] == "HSBA"
    assert body["items"][0]["provider_symbol"] == "HSBA.L"

    listed = client.get("/securities", params={"limit": 1, "offset": 0})
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 2
    assert len(listed.json()["items"]) == 1
    second_page = client.get("/securities", params={"limit": 1, "offset": 1})
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert second_page.json()["items"][0]["id"] != listed.json()["items"][0]["id"]

    loaded = client.get(f"/securities/id/{apple.id}")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["id"] == str(apple.id)
    assert loaded.json()["provider"] == "seed"

    rejected = client.get("/securities", params={"asset_type": "crypto"})
    assert rejected.status_code == 422
