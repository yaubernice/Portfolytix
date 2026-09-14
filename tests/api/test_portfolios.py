from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import User


def test_create_list_get_patch_delete_portfolio(
    client: TestClient, user: User
) -> None:
    created = client.post(
        "/portfolios",
        json={
            "user_id": str(user.id),
            "name": "Core",
            "description": "taxable",
        },
    )
    assert created.status_code == 201
    body = created.json()
    portfolio_id = body["id"]
    assert body["name"] == "Core"
    assert body["user_id"] == str(user.id)

    listed = client.get("/portfolios", params={"user_id": str(user.id)})
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


def test_list_requires_user_id(client: TestClient) -> None:
    response = client.get("/portfolios")
    assert response.status_code == 422


def test_list_does_not_include_other_users_portfolios(
    client: TestClient, user: User, other_user: User
) -> None:
    client.post("/portfolios", json={"user_id": str(user.id), "name": "A"})
    client.post("/portfolios", json={"user_id": str(other_user.id), "name": "B"})
    listed = client.get("/portfolios", params={"user_id": str(user.id)})
    names = {row["name"] for row in listed.json()}
    assert names == {"A"}


def test_unknown_user_and_portfolio_are_not_found(client: TestClient) -> None:
    missing_user = client.post(
        "/portfolios",
        json={"user_id": str(uuid4()), "name": "Core"},
    )
    assert missing_user.status_code == 404

    missing_portfolio = client.get(f"/portfolios/{uuid4()}")
    assert missing_portfolio.status_code == 404


def test_empty_patch_is_rejected(client: TestClient, user: User) -> None:
    created = client.post(
        "/portfolios",
        json={"user_id": str(user.id), "name": "Core"},
    )
    response = client.patch(f"/portfolios/{created.json()['id']}", json={})
    assert response.status_code == 422
