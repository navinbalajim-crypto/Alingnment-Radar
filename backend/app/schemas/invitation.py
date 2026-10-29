"""Group invitation redemption and onboarding schemas."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.schemas.auth import TokenResponse


class InvitationPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_id: uuid.UUID
    group_title: str
    invited_by_username: str
    is_valid: bool
    expires_at: datetime


class InvitationRequestCodeRequest(BaseModel):
    email: EmailStr


class InvitationVerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class InvitationVerifyCodeResponse(BaseModel):
    message: str
    is_existing_user: bool
    group_id: uuid.UUID
    group_title: str
    registration_ticket: Optional[str] = None
    tokens: Optional[TokenResponse] = None


class InvitationCompleteRegistrationRequest(BaseModel):
    registration_ticket: str = Field(..., description="Signed token from invitation verification")
    username: str = Field(..., min_length=3, max_length=30)
    display_name: Optional[str] = None
