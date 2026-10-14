from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_quote_store
from app.api.routes import health
from app.main import app
from app.quotes.store import MemoryQuoteStore

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_database_and_disabled_redis(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(health, "redis_readiness", lambda: "disabled")
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"postgresql": "ok", "redis": "disabled"},
    }


def test_readiness_fails_when_redis_is_unavailable(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(health, "redis_readiness", lambda: "error")
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_status_summarizes_provider_cache_and_worker(client: TestClient) -> None:
    store = MemoryQuoteStore()
    store.put_worker_heartbeat(
        {
            "provider": "simulator",
            "symbol_count": 1,
            "active_subscriptions": ["AAPL"],
            "last_publish_at": datetime.now(UTC).isoformat(),
            "last_poll_at": datetime.now(UTC).isoformat(),
            "state": "running",
        }
    )
    app.dependency_overrides[get_quote_store] = lambda: store
    response = client.get("/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"]["name"] == "simulator"
    assert body["worker"]["symbol_count"] == 1
    assert "hit_rate" in body["cache"]
    assert "metrics" in body
