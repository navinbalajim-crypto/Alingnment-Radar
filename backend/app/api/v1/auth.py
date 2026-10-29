"""Authentication endpoints under /api/v1/auth."""

from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    CompleteRegistrationRequest,
    ForgotPasswordRequest,
    LogoutRequest,
    MessageResponse,
    PasswordLoginRequest,
    RefreshTokenRequest,
    RequestCodeRequest,
    RequestCodeResponse,
    ResetPasswordCompleteRequest,
    ResetPasswordVerifyRequest,
    ResetPasswordVerifyResponse,
    SetPasswordRequest,
    TokenResponse,
    VerifyCodeRequest,
    VerifyRegisterCodeResponse,
)
from app.schemas.oauth import (
    GoogleAuthCallbackRequest,
    GoogleAuthUrlResponse,
)
from app.services.auth_service import AuthService
from app.services.google_auth_service import GoogleAuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/google/url", response_model=GoogleAuthUrlResponse, status_code=status.HTTP_200_OK)
async def get_google_auth_url(
    redirect_uri: Optional[str] = None,
    prompt: str = "consent",
    db: AsyncSession = Depends(get_db),
):
    """Retrieve Google OAuth consent URL with cryptographic state parameter."""
    google_service = GoogleAuthService(db)
    return google_service.get_authorization_url(redirect_uri=redirect_uri, prompt=prompt)


@router.post("/google/callback", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def authenticate_google_callback(
    payload: GoogleAuthCallbackRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Exchange authorization code returned from Google for application authentication session."""
    google_service = GoogleAuthService(db)
    client_ip = request.client.host if request.client else None
    return await google_service.authenticate_with_code(
        code=payload.code,
        state=payload.state,
        redirect_uri=payload.redirect_uri,
        user_agent=user_agent,
        ip_address=client_ip,
    )


@router.post("/register/request-code", response_model=RequestCodeResponse, status_code=status.HTTP_200_OK)
async def request_registration_code(
    payload: RequestCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a single-use verification code sent to email for user registration."""
    auth_service = AuthService(db)
    return await auth_service.request_registration_code(payload.email)


@router.post("/register/verify-code", response_model=VerifyRegisterCodeResponse, status_code=status.HTTP_200_OK)
async def verify_registration_code(
    payload: VerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify email registration code and receive short-lived registration ticket."""
    auth_service = AuthService(db)
    return await auth_service.verify_registration_code(payload.email, payload.code)


@router.post("/register/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def complete_registration(
    payload: CompleteRegistrationRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Complete registration with verified email ticket, choose unique username, and issue session."""
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    return await auth_service.complete_registration(
        registration_ticket=payload.registration_ticket,
        raw_username=payload.username,
        display_name=payload.display_name,
        password=payload.password,
        user_agent=user_agent,
        ip_address=client_ip,
    )


@router.post("/login/password", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login_with_password(
    payload: PasswordLoginRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Sign into an existing account using username/email and password."""
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    return await auth_service.login_with_password(
        identifier=payload.username,
        password=payload.password,
        user_agent=user_agent,
        ip_address=client_ip,
    )


@router.post("/password/forgot", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def request_password_reset(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a time-limited password recovery code sent to email."""
    auth_service = AuthService(db)
    return await auth_service.request_password_reset(payload.email)


@router.post("/password/verify-code", response_model=ResetPasswordVerifyResponse, status_code=status.HTTP_200_OK)
async def verify_password_reset_code(
    payload: ResetPasswordVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify password recovery code and receive reset ticket."""
    auth_service = AuthService(db)
    return await auth_service.verify_password_reset_code(payload.email, payload.code)


@router.post("/password/reset", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def complete_password_reset(
    payload: ResetPasswordCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set new password using verified recovery ticket."""
    auth_service = AuthService(db)
    return await auth_service.complete_password_reset(payload.reset_ticket, payload.new_password)


@router.post("/password/set", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def set_user_password(
    payload: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Allow an authenticated user (e.g. email-code or Google-authenticated) to set a password."""
    auth_service = AuthService(db)
    return await auth_service.set_user_password(current_user.id, payload.new_password)


@router.post("/login/request-code", response_model=RequestCodeResponse, status_code=status.HTTP_200_OK)
async def request_login_code(
    payload: RequestCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a single-use email verification code to sign into an existing account."""
    auth_service = AuthService(db)
    return await auth_service.request_login_code(payload.email)


@router.post("/login/verify-code", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def verify_login_code(
    payload: VerifyCodeRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Verify sign-in email code and receive access and refresh token session."""
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    return await auth_service.verify_login_code(
        raw_email=payload.email,
        code=payload.code,
        user_agent=user_agent,
        ip_address=client_ip,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Rotate active refresh token and issue a fresh access token."""
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    return await auth_service.refresh_tokens(
        raw_refresh_token=payload.refresh_token,
        user_agent=user_agent,
        ip_address=client_ip,
    )


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke refresh session on logout."""
    auth_service = AuthService(db)
    await auth_service.logout(payload.refresh_token)
    return MessageResponse(message="Successfully signed out.")

