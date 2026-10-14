from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.models import Security, User


def test_watchlist_is_private_and_rejects_a_duplicate_security(
    client: TestClient,
    user: User,
    other_user: User,
    apple: Security,
) -> None:
    created = client.post("/watchlists", json={"name": "Ideas"})
    assert created.status_code == 201, created.text
    watchlist_id = created.json()["id"]
    assert created.json()["item_count"] == 0

    added = client.post(
        f"/watchlists/{watchlist_id}/items",
        json={"security_id": str(apple.id)},
    )
    assert added.status_code == 201, added.text
    assert added.json()["ticker"] == "AAPL"

    duplicate = client.post(
        f"/watchlists/{watchlist_id}/items",
        json={"security_id": str(apple.id)},
    )
    assert duplicate.status_code == 409

    detail = client.get(f"/watchlists/{watchlist_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["item_count"] == 1
    assert body["items"][0]["security_id"] == str(apple.id)

    renamed = client.patch(
        f"/watchlists/{watchlist_id}",
        json={"name": "Core ideas"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Core ideas"

    headers = {"Authorization": f"Bearer {create_access_token(other_user.id)}"}
    hidden = client.get(f"/watchlists/{watchlist_id}", headers=headers)
    assert hidden.status_code == 404
    stolen = client.post(
        f"/watchlists/{watchlist_id}/items",
        json={"security_id": str(apple.id)},
        headers=headers,
    )
    assert stolen.status_code == 404
    assert client.patch(
        f"/watchlists/{watchlist_id}",
        json={"name": "Stolen"},
        headers=headers,
    ).status_code == 404
    assert client.delete(
        f"/watchlists/{watchlist_id}/items/{apple.id}",
        headers=headers,
    ).status_code == 404
    assert client.delete(
        f"/watchlists/{watchlist_id}",
        headers=headers,
    ).status_code == 404

    missing_security = client.post(
        f"/watchlists/{watchlist_id}/items",
        json={"security_id": "00000000-0000-4000-8000-000000000099"},
    )
    assert missing_security.status_code == 404

    removed = client.delete(f"/watchlists/{watchlist_id}/items/{apple.id}")
    assert removed.status_code == 204
    empty = client.get(f"/watchlists/{watchlist_id}")
    assert empty.json()["item_count"] == 0

    deleted = client.delete(f"/watchlists/{watchlist_id}")
    assert deleted.status_code == 204
    gone = client.get(f"/watchlists/{watchlist_id}")
    assert gone.status_code == 404

    listed = client.get("/watchlists")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert user.id != other_user.id
