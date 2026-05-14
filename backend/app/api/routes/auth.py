from fastapi import APIRouter, Depends

from app.api.auth import require_authenticated_user
from app.models.chat import (
    AuthCodeSendRequest,
    AuthCodeSendResponse,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    LogoutResponse,
    UserProfile,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/code/send", response_model=AuthCodeSendResponse)
def send_code(request: AuthCodeSendRequest) -> AuthCodeSendResponse:
    return auth_service.send_code(request)


@router.post("/register", response_model=AuthTokenResponse)
def register(request: AuthRegisterRequest) -> AuthTokenResponse:
    user = auth_service.register(request)
    token = auth_service.create_access_token(user)
    return AuthTokenResponse(access_token=token, user=user)


@router.post("/login", response_model=AuthTokenResponse)
def login(request: AuthLoginRequest) -> AuthTokenResponse:
    user = auth_service.login(request)
    token = auth_service.create_access_token(user)
    return AuthTokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserProfile)
def me(user: UserProfile = Depends(require_authenticated_user)) -> UserProfile:
    return user


@router.post("/logout", response_model=LogoutResponse)
def logout(_: UserProfile = Depends(require_authenticated_user)) -> LogoutResponse:
    return LogoutResponse(success=True)
