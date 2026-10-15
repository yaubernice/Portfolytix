from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_quote_store
from app.core.security import create_access_token
from app.db.models import Security, User
from app.main import app
from app.quotes.store import MemoryQuoteStore
from tests.api.helpers import create_portfolio


def test_news_is_cached_and_not_invented(
    client: TestClient,
    apple: Security,
) -> None:
    empty = client.get("/news", params={"ticker": "AAPL"})
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == []
    assert empty.json()["provider"] == "none"

    store = MemoryQuoteStore()
    store.put_news(
        "AAPL",
        [
            {
                "headline": "Apple updates guidance",
                "summary": "Short",
                "source": "Reuters",
                "url": "https://example.test/a",
                "published_at": "2026-10-02T12:00:00+00:00",
                "tickers": ["AAPL"],
                "sentiment": "Bullish",
                "provider": "finnhub",
            }
        ],
    )
    app.dependency_overrides[get_quote_store] = lambda: store
    by_id = client.get(f"/securities/id/{apple.id}/news")
    assert by_id.status_code == 200, by_id.text
    body = by_id.json()
    assert body["security_id"] == str(apple.id)
    assert body["provider"] == "finnhub"
    assert body["items"][0]["sentiment"] == "Bullish"
    assert body["items"][0]["tickers"] == ["AAPL"]

    missing = client.get(
        "/securities/id/00000000-0000-4000-8000-000000000099/news"
    )
    assert missing.status_code == 404


def test_portfolio_news_uses_cached_headlines_for_open_positions(
    client: TestClient,
    sqlite_session: Session,
    user: User,
    other_user: User,
    apple: Security,
) -> None:
    sqlite_session.commit()
    store = MemoryQuoteStore()
    store.put_news(
        "AAPL",
        [
            {
                "headline": "Apple updates guidance",
                "summary": "Stored summary",
                "source": "Reuters",
                "url": "https://example.test/a",
                "published_at": "2026-10-02T12:00:00+00:00",
                "tickers": ["AAPL"],
                "sentiment": None,
                "provider": "yahoo",
                "image_url": "https://example.test/photo.jpg",
            }
        ],
    )
    app.dependency_overrides[get_quote_store] = lambda: store
    portfolio = create_portfolio(client, user.id)
    bought = client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "quantity": "1",
            "price": "100",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    )
    assert bought.status_code == 201, bought.text
    response = client.get(f"/portfolios/{portfolio['id']}/news")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "yahoo"
    assert body["items"][0]["image_url"] == "https://example.test/photo.jpg"
    assert body["items"][0]["summary"] == "Stored summary"
    assert body["unavailable"] == []

    hidden = client.get(
        f"/portfolios/{portfolio['id']}/news",
        headers={"Authorization": f"Bearer {create_access_token(other_user.id)}"},
    )
    assert hidden.status_code == 404
