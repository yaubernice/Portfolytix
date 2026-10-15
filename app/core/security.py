from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import AuthenticationError

# creates a password-hashing object using the recommended algorithm
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password with Argon2; plaintext is never stored."""
    # hashes the password using the password-hashing object
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    # verfy if the password could have produced the stored hash
    try:
        return password_hash.verify(password, encoded_hash)
    except (TypeError, ValueError):
        # Legacy/seed placeholders are not valid encoded hashes.
        return False


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    # token expire time
    expires = now + timedelta(minutes=settings.jwt_access_token_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access", #token type
        "iss": settings.jwt_issuer, #token issuer
        "iat": now, #token issue time
        "exp": expires, #token expire time
    }
    return jwt.encode( #create the JWT string
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key, #verify signature
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer, #verify issuer
            # verify required fields
            options={"require": ["sub", "type", "iss", "iat", "exp"]},
        )
        if payload["type"] != "access":
            raise AuthenticationError("Invalid access token")
        return UUID(payload["sub"])
    except (
        jwt.InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise AuthenticationError("Invalid or expired access token") from exc
