from uuid import UUID

from fastapi.testclient import TestClient


def create_portfolio(
    client: TestClient, user_id: UUID, name: str = "Core"
) -> dict[str, object]:
    response = client.post(
        "/portfolios",
        json={"name": name, "description": "taxable"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user_id"] == str(user_id)
    return body
