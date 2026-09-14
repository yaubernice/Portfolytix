from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Security, User
from app.main import app


@pytest.fixture
def client(sqlite_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        try:
            yield sqlite_session
            sqlite_session.commit()
        except Exception:
            sqlite_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(sqlite_session: Session) -> User:
    row = User(email="alice@example.com", password_hash="not-a-real-hash")
    sqlite_session.add(row)
    sqlite_session.flush()
    return row


@pytest.fixture
def other_user(sqlite_session: Session) -> User:
    row = User(email="bob@example.com", password_hash="not-a-real-hash")
    sqlite_session.add(row)
    sqlite_session.flush()
    return row


@pytest.fixture
def apple(sqlite_session: Session) -> Security:
    row = Security(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        currency="USD",
    )
    sqlite_session.add(row)
    sqlite_session.flush()
    return row
