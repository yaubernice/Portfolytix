from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import create_access_token
from app.db.models import Security, User
from app.main import app

DEFAULT_USER_ID = UUID("00000000-0000-4000-8000-000000000101")
OTHER_USER_ID = UUID("00000000-0000-4000-8000-000000000102")


def _get_or_create_user(
    session: Session,
    user_id: UUID,
    email: str,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            email=email,
            password_hash="not-a-real-hash",
        )
        session.add(user)
        session.flush()
    return user


@pytest.fixture
def client(sqlite_session: Session) -> Iterator[TestClient]:
    _get_or_create_user(
        sqlite_session,
        DEFAULT_USER_ID,
        "alice@example.com",
    )
    sqlite_session.commit()

    def override_get_db() -> Iterator[Session]:
        try:
            yield sqlite_session
            sqlite_session.commit()
        except Exception:
            sqlite_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    headers = {
        "Authorization": f"Bearer {create_access_token(DEFAULT_USER_ID)}",
    }
    with TestClient(app, headers=headers) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(sqlite_session: Session) -> User:
    return _get_or_create_user(
        sqlite_session,
        DEFAULT_USER_ID,
        "alice@example.com",
    )


@pytest.fixture
def other_user(sqlite_session: Session) -> User:
    return _get_or_create_user(
        sqlite_session,
        OTHER_USER_ID,
        "bob@example.com",
    )


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
