from fastapi.testclient import TestClient


def test_cache_stats_when_cache_is_disabled(client: TestClient) -> None:
    response = client.get("/cache/stats")
    assert response.status_code == 200
    assert response.json() == {
        "hits": 0,
        "misses": 0,
        "sets": 0,
        "invalidations": 0,
        "errors": 0,
        "requests": 0,
        "hit_rate": 0.0,
    }
