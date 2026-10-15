from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import Portfolio, Price, Security, Transaction, User
from app.services.analytics_service import AnalyticsService
from tests.fakes import FakeCache


def _portfolio_with_history(session: Session) -> Portfolio:
    user = User(email="cache@example.com", password_hash="not-a-real-hash")
    security = Security(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    session.add_all([user, security])
    session.flush()
    portfolio = Portfolio(user_id=user.id, name="Cached")
    session.add(portfolio)
    session.flush()
    session.add(
        Transaction(
            portfolio_id=portfolio.id,
            security_id=security.id,
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
    )
    for day, close in ((2, "100"), (3, "110")):
        price = Decimal(close)
        session.add(
            Price(
                security_id=security.id,
                timestamp=datetime(2024, 1, day, tzinfo=UTC),
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=price,
                volume=1,
            )
        )
    session.flush()
    return portfolio


def test_analytics_second_read_is_a_cache_hit(sqlite_session: Session) -> None:
    portfolio = _portfolio_with_history(sqlite_session)
    cache = FakeCache()
    service = AnalyticsService(sqlite_session, portfolio.user_id, cache)

    first = service.get_analytics(portfolio.id)

    def fail_if_database_is_called(*_args, **_kwargs):
        raise AssertionError("transaction repository should not run on cache hit")

    service.transactions.list_for_portfolio = fail_if_database_is_called
    second = service.get_analytics(portfolio.id)

    assert second == first
    assert cache.stats()["misses"] == 1
    assert cache.stats()["hits"] == 1
    assert cache.stats()["sets"] == 1


def test_analytics_key_tracks_portfolio_and_price_versions(
    sqlite_session: Session,
) -> None:
    portfolio = _portfolio_with_history(sqlite_session)
    cache = FakeCache()
    service = AnalyticsService(sqlite_session, portfolio.user_id, cache)

    original = service._cache_key(portfolio.id)
    cache.bump_version(f"portfolio:{portfolio.id}")
    portfolio_changed = service._cache_key(portfolio.id)
    cache.bump_version("prices")
    prices_changed = service._cache_key(portfolio.id)

    assert original != portfolio_changed
    assert portfolio_changed != prices_changed
