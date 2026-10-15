from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_auth_service, get_current_user
from app.db.models import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    return service.register(payload)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    return service.login(payload)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
