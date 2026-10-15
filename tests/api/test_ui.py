from fastapi.testclient import TestClient


def test_demo_ui_is_served(client: TestClient) -> None:
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "Portfolio demo" in response.text
    assert "/ui/app.js" in response.text
