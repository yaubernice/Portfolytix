from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.models import Security, User


def test_create_list_get_patch_delete_portfolio(
    client: TestClient, user: User
) -> None:
    created = client.post(
        "/portfolios",
        json={
            "name": "Core",
            "description": "taxable",
        },
    )
    assert created.status_code == 201
    body = created.json()
    portfolio_id = body["id"]
    assert body["name"] == "Core"
    assert body["user_id"] == str(user.id)

    listed = client.get("/portfolios")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"/portfolios/{portfolio_id}")
    assert detail.status_code == 200
    assert detail.json()["holdings"] == []

    patched = client.patch(
        f"/portfolios/{portfolio_id}",
        json={"name": "Retirement"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Retirement"
    assert patched.json()["description"] == "taxable"

    deleted = client.delete(f"/portfolios/{portfolio_id}")
    assert deleted.status_code == 204
    missing = client.get(f"/portfolios/{portfolio_id}")
    assert missing.status_code == 404


def test_list_uses_authenticated_user(client: TestClient) -> None:
    response = client.get("/portfolios")
    assert response.status_code == 200


def test_list_does_not_include_other_users_portfolios(
    client: TestClient, user: User, other_user: User
) -> None:
    client.post("/portfolios", json={"name": "A"})
    other_headers = {
        "Authorization": f"Bearer {create_access_token(other_user.id)}",
    }
    client.post("/portfolios", json={"name": "B"}, headers=other_headers)
    listed = client.get("/portfolios")
    names = {row["name"] for row in listed.json()}
    assert names == {"A"}


def test_user_id_cannot_be_spoofed_and_missing_portfolio_is_404(
    client: TestClient,
) -> None:
    spoofed_user = client.post(
        "/portfolios",
        json={"user_id": str(uuid4()), "name": "Core"},
    )
    assert spoofed_user.status_code == 422

    missing_portfolio = client.get(f"/portfolios/{uuid4()}")
    assert missing_portfolio.status_code == 404


def test_empty_patch_is_rejected(client: TestClient, user: User) -> None:
    created = client.post(
        "/portfolios",
        json={"name": "Core"},
    )
    response = client.patch(f"/portfolios/{created.json()['id']}", json={})
    assert response.status_code == 422


def test_other_user_cannot_access_portfolio_resources(
    client: TestClient,
    user: User,
    other_user: User,
    apple: Security,
) -> None:
    portfolio = client.post("/portfolios", json={"name": "Core"}).json()
    portfolio_id = portfolio["id"]
    headers = {
        "Authorization": f"Bearer {create_access_token(other_user.id)}",
    }

    requests = [
        client.get(f"/portfolios/{portfolio_id}", headers=headers),
        client.patch(
            f"/portfolios/{portfolio_id}",
            json={"name": "Stolen"},
            headers=headers,
        ),
        client.get(
            f"/portfolios/{portfolio_id}/transactions",
            headers=headers,
        ),
        client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json={
                "ticker": apple.ticker,
                "transaction_type": "BUY",
                "quantity": "1",
                "price": "100",
            },
            headers=headers,
        ),
        client.get(
            f"/portfolios/{portfolio_id}/holdings",
            headers=headers,
        ),
        client.get(
            f"/portfolios/{portfolio_id}/analytics",
            headers=headers,
        ),
        client.delete(f"/portfolios/{portfolio_id}", headers=headers),
    ]

    assert {response.status_code for response in requests} == {404}
    assert client.get(f"/portfolios/{portfolio_id}").status_code == 200
