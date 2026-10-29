"""Google Meet meeting creation and invitation endpoints under /api/v1/conversations/{conversation_id}/meet."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.meeting import GoogleMeetCallbackRequest, MeetingCreateRequest, MeetingCreateResponse, MeetingInvitationRead
from app.services.google_meet_service import GoogleMeetService

router = APIRouter(tags=["Google Meet"])


@router.post(
    "/conversations/{conversation_id}/meet",
    response_model=MeetingCreateResponse,
    status_code=status.HTTP_200_OK,
)
async def create_google_meet(
    conversation_id: uuid.UUID,
    payload: Optional[MeetingCreateRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate or retrieve a Google Meet meeting space for a direct or group conversation.
    If the user has not granted Google Meet permissions, returns requires_auth=true
    and the Google authorization URL.
    """
    service = GoogleMeetService(db)
    client_token = payload.client_token if payload else None
    redirect_uri = payload.redirect_uri if payload else None
    fallback_instant = payload.fallback_instant if payload else False
    return await service.create_or_get_meeting(
        conversation_id=conversation_id,
        user=current_user,
        client_token=client_token,
        redirect_uri=redirect_uri,
        fallback_instant=fallback_instant,
    )


@router.get(
    "/conversations/{conversation_id}/meet/auth-url",
    status_code=status.HTTP_200_OK,
)
async def get_meet_auth_url(
    conversation_id: uuid.UUID,
    redirect_uri: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get Google OAuth URL requesting Meet scopes for this user and conversation."""
    service = GoogleMeetService(db)
    url = service.get_meet_authorization_url(
        conversation_id=conversation_id,
        user_id=current_user.id,
        redirect_uri=redirect_uri,
    )
    return {"authorization_url": url}


@router.post(
    "/auth/google/meet/callback",
    status_code=status.HTTP_200_OK,
)
async def handle_meet_oauth_callback(
    payload: Optional[GoogleMeetCallbackRequest] = None,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    redirect_uri: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exchange authorization code and link Google Meet permissions to current user."""
    auth_code = (payload.code if payload and payload.code else None) or code
    oauth_state = (payload.state if payload and payload.state else None) or state
    oauth_redirect_uri = (payload.redirect_uri if payload and payload.redirect_uri else None) or redirect_uri

    if not auth_code:
        raise HTTPException(status_code=422, detail="Authorization code is required.")

    service = GoogleMeetService(db)
    return await service.connect_google_meet(
        code=auth_code,
        state=oauth_state,
        user_id=current_user.id,
        redirect_uri=oauth_redirect_uri,
    )
