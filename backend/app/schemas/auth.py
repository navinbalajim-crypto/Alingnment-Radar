"""Authentication request and response schemas."""

import uuid
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RequestCodeRequest(BaseModel):
    email: EmailStr = Field(..., description="User's email address")


class RequestCodeResponse(BaseModel):
    message: str
    email: str
    cooldown_seconds: int


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class VerifyRegisterCodeResponse(BaseModel):
    message: str
    registration_ticket: str
    email: str


class CompleteRegistrationRequest(BaseModel):
    registration_ticket: str = Field(..., description="Signed token issued upon email verification")
    username: str = Field(..., min_length=3, max_length=30, description="Unique username")
    display_name: Optional[str] = Field(None, max_length=100, description="Optional public display name")
    password: Optional[str] = Field(None, min_length=8, max_length=128, description="User password (min 8 chars)")


class PasswordLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username or email")
    password: str = Field(..., min_length=1, max_length=128, description="User password")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email address")


class ResetPasswordVerifyRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class ResetPasswordVerifyResponse(BaseModel):
    message: str
    reset_ticket: str
    email: str


class ResetPasswordCompleteRequest(BaseModel):
    reset_ticket: str = Field(..., description="Signed token issued upon reset code verification")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")


class SetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")


class UserTokenPayload(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    has_password: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserTokenPayload
    has_password: bool = False


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Active refresh token")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token to invalidate")


class MessageResponse(BaseModel):
    message: str
