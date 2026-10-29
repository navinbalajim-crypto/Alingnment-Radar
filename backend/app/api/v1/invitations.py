"""Group invitation onboarding and code verification endpoints under /api/v1/invitations."""

from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.auth import RequestCodeResponse, TokenResponse
from app.schemas.invitation import (
    InvitationCompleteRegistrationRequest,
    InvitationPreviewResponse,
    InvitationRequestCodeRequest,
    InvitationVerifyCodeRequest,
    InvitationVerifyCodeResponse,
)
from app.services.invitation_service import InvitationService

router = APIRouter(prefix="/invitations", tags=["Invitations"])


@router.get("/{token}", response_model=InvitationPreviewResponse, status_code=status.HTTP_200_OK)
async def preview_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve public invitation preview showing group title and validity."""
    invitation_service = InvitationService(db)
    return await invitation_service.preview_invitation(token)


@router.post("/{token}/request-code", response_model=RequestCodeResponse, status_code=status.HTTP_200_OK)
async def request_invitation_code(
    token: str,
    payload: InvitationRequestCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a single-use verification code sent to email specifically for joining this group."""
    invitation_service = InvitationService(db)
    return await invitation_service.request_invitation_code(token=token, raw_email=payload.email)


@router.post("/{token}/verify-code", response_model=InvitationVerifyCodeResponse, status_code=status.HTTP_200_OK)
async def verify_invitation_code(
    token: str,
    payload: InvitationVerifyCodeRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify invitation code. If existing user, adds to group and returns session.
    If new user, returns registration ticket to complete onboarding.
    """
    invitation_service = InvitationService(db)
    client_ip = request.client.host if request.client else None
    return await invitation_service.verify_invitation_code(
        token=token,
        raw_email=payload.email,
        code=payload.code,
        user_agent=user_agent,
        ip_address=client_ip,
    )


@router.post("/{token}/complete-registration", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def complete_invitation_registration(
    token: str,
    payload: InvitationCompleteRegistrationRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Complete registration with invitation ticket, join group, and issue authenticated session."""
    invitation_service = InvitationService(db)
    client_ip = request.client.host if request.client else None
    return await invitation_service.complete_invitation_registration(
        token=token,
        registration_ticket=payload.registration_ticket,
        raw_username=payload.username,
        display_name=payload.display_name,
        user_agent=user_agent,
        ip_address=client_ip,
    )
