from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.db.models import User


def test_register_login_and_me(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    registered = client.post(
        "/auth/register",
        json={"email": "NEW@Example.com", "password": "strong-password"},
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["email"] == "new@example.com"

    user = sqlite_session.scalar(
        select(User).where(User.email == "new@example.com")
    )
    assert user is not None
    assert user.password_hash != "strong-password"
    assert user.password_hash.startswith("$argon2")
    assert verify_password("strong-password", user.password_hash)

    logged_in = client.post(
        "/auth/login",
        json={"email": "new@example.com", "password": "strong-password"},
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["access_token"]
    assert logged_in.json()["token_type"] == "bearer"

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["id"] == registered.json()["id"]
    assert "password_hash" not in me.json()


def test_duplicate_registration_is_conflict(client: TestClient) -> None:
    payload = {"email": "duplicate@example.com", "password": "password-123"}
    assert client.post("/auth/register", json=payload).status_code == 201
    duplicate = client.post(
        "/auth/register",
        json={"email": "DUPLICATE@example.com", "password": "password-123"},
    )
    assert duplicate.status_code == 409


def test_login_uses_generic_error(client: TestClient) -> None:
    unknown = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "Invalid email or password"
    assert unknown.headers["www-authenticate"] == "Bearer"


def test_protected_route_requires_bearer_token(client: TestClient) -> None:
    response = client.get(
        "/portfolios",
        headers={"Authorization": ""},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401


def test_wrong_password_matches_unknown_email(client: TestClient) -> None:
    registered = client.post(
        "/auth/register",
        json={"email": "known@example.com", "password": "password-123"},
    )
    assert registered.status_code == 201
    assert "password" not in registered.json()

    wrong = client.post(
        "/auth/login",
        json={"email": "known@example.com", "password": "not-the-password"},
    )
    unknown = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "not-the-password"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "password-123"},
        {"email": "short@example.com", "password": "short"},
        {
            "email": "extra@example.com",
            "password": "password-123",
            "role": "admin",
        },
    ],
)
def test_register_rejects_invalid_payload(
    client: TestClient,
    payload: dict[str, str],
) -> None:
    assert client.post("/auth/register", json=payload).status_code == 422


def test_expired_token_is_rejected(client: TestClient, user: User) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "iss": settings.jwt_issuer,
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
