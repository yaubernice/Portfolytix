from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Portfolio, Price, Security, Transaction, User


def _user(session: Session, email: str = "alice@example.com") -> User:
    user = User(email=email, password_hash="not-a-real-hash")
    session.add(user)
    session.flush()
    return user


def _security(session: Session, ticker: str = "AAPL") -> Security:
    security = Security(
        ticker=ticker,
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    session.add(security)
    session.flush()
    return security


def test_price_round_trip_uses_decimal(sqlite_session) -> None:
    security = _security(sqlite_session)
    bar = Price(
        security_id=security.id,
        timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        open=Decimal("185.250000"),
        high=Decimal("186.000000"),
        low=Decimal("184.500000"),
        close=Decimal("185.750000"),
        adjusted_close=Decimal("185.750000"),
        volume=50_000_000,
    )
    sqlite_session.add(bar)
    sqlite_session.flush()
    sqlite_session.refresh(bar)
    assert bar.close == Decimal("185.750000")
    assert isinstance(bar.close, Decimal)


def test_duplicate_ticker_is_rejected(sqlite_session) -> None:
    _security(sqlite_session, "AAPL")
    with pytest.raises(IntegrityError):
        _security(sqlite_session, "AAPL")


def test_duplicate_email_is_rejected(sqlite_session) -> None:
    _user(sqlite_session, "alice@example.com")
    with pytest.raises(IntegrityError):
        _user(sqlite_session, "alice@example.com")


def test_duplicate_price_bar_is_rejected(sqlite_session) -> None:
    security = _security(sqlite_session)
    stamp = datetime(2024, 1, 2, tzinfo=UTC)
    kwargs = {
        "security_id": security.id,
        "timestamp": stamp,
        "open": Decimal("10"),
        "high": Decimal("11"),
        "low": Decimal("9"),
        "close": Decimal("10.5"),
        "adjusted_close": Decimal("10.5"),
        "volume": 1,
    }
    sqlite_session.add(Price(**kwargs))
    sqlite_session.flush()
    sqlite_session.add(Price(id=uuid4(), **kwargs))
    with pytest.raises(IntegrityError):
        sqlite_session.flush()


def test_high_below_low_is_rejected(sqlite_session) -> None:
    security = _security(sqlite_session)
    sqlite_session.add(
        Price(
            security_id=security.id,
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("9"),
            low=Decimal("11"),
            close=Decimal("10"),
            adjusted_close=Decimal("10"),
            volume=1,
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()


def test_invalid_transaction_type_is_rejected(sqlite_session) -> None:
    user = _user(sqlite_session)
    portfolio = Portfolio(user_id=user.id, name="Core")
    sqlite_session.add(portfolio)
    security = _security(sqlite_session)
    sqlite_session.flush()
    sqlite_session.add(
        Transaction(
            portfolio_id=portfolio.id,
            security_id=security.id,
            transaction_type="HOLD",
            quantity=Decimal("1"),
            price=Decimal("10"),
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()


def test_zero_quantity_is_rejected(sqlite_session) -> None:
    user = _user(sqlite_session)
    portfolio = Portfolio(user_id=user.id, name="Core")
    sqlite_session.add(portfolio)
    security = _security(sqlite_session)
    sqlite_session.flush()
    sqlite_session.add(
        Transaction(
            portfolio_id=portfolio.id,
            security_id=security.id,
            transaction_type="BUY",
            quantity=Decimal("0"),
            price=Decimal("10"),
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()


def test_missing_security_fk_is_rejected(sqlite_session) -> None:
    user = _user(sqlite_session)
    portfolio = Portfolio(user_id=user.id, name="Core")
    sqlite_session.add(portfolio)
    sqlite_session.flush()
    sqlite_session.add(
        Transaction(
            portfolio_id=portfolio.id,
            security_id=uuid4(),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("10"),
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()


def test_deleting_user_cascades_portfolios(sqlite_session) -> None:
    user = _user(sqlite_session)
    sqlite_session.add(Portfolio(user_id=user.id, name="Core"))
    sqlite_session.flush()
    sqlite_session.delete(user)
    sqlite_session.flush()
    remaining = sqlite_session.scalars(select(Portfolio)).all()
    assert remaining == []


def test_deleting_traded_security_is_restricted(sqlite_session) -> None:
    user = _user(sqlite_session)
    portfolio = Portfolio(user_id=user.id, name="Core")
    sqlite_session.add(portfolio)
    security = _security(sqlite_session)
    sqlite_session.flush()
    sqlite_session.add(
        Transaction(
            portfolio_id=portfolio.id,
            security_id=security.id,
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("185"),
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
    )
    sqlite_session.flush()
    sqlite_session.delete(security)
    with pytest.raises(IntegrityError):
        sqlite_session.flush()
