from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, payload: RegisterRequest) -> UserOut:
        if self.users.get_by_email(str(payload.email)) is not None:
            raise ConflictError("An account with that email already exists")
        user = User(
            email=str(payload.email),
            # turn password to an Argon2 hash for database store
            password_hash=hash_password(payload.password),
        )
        try:
            # repo add the user to database session and flush it
            saved = self.users.add(user)
        except IntegrityError as exc:
            # The unique email constraint resolves concurrent registrations
            # like if two insert same email at the same time
            self.session.rollback()
            raise ConflictError(
                "An account with that email already exists"
            ) from exc
        return UserOut.model_validate(saved)

    def login(self, payload: LoginRequest) -> TokenOut:
        user = self.users.get_by_email(str(payload.email)) #database lookup by email
        if user is None or not verify_password(
            payload.password,
            user.password_hash,
        ):
            # Use one response for unknown email and wrong password.
            raise AuthenticationError("Invalid email or password")
        return TokenOut(
            access_token=create_access_token(user.id), #create the access token
            # token expire time in seconds
            expires_in=settings.jwt_access_token_minutes * 60,
        )
