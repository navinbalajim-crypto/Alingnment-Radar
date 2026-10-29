"""Google Meet meeting invitation schemas."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.message import MessageRead


class MeetingInvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    creator_id: Optional[uuid.UUID] = None
    creator_username: Optional[str] = None
    message_id: Optional[uuid.UUID] = None
    provider: str = "google_meet"
    meeting_uri: str
    meeting_code: Optional[str] = None
    space_name: Optional[str] = None
    status: str = "active"
    client_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MeetingCreateRequest(BaseModel):
    client_token: Optional[str] = Field(None, max_length=64, description="Client idempotency key")
    redirect_uri: Optional[str] = Field(None, description="Frontend origin's OAuth callback URL, so the Google consent redirect lands back on the same origin the user is browsing from")
    fallback_instant: Optional[bool] = Field(False, description="Generate instant Google Meet link without requiring OAuth")


class MeetingCreateResponse(BaseModel):
    requires_auth: bool = Field(False, description="True if Google OAuth with Meet scope is needed")
    authorization_url: Optional[str] = Field(None, description="Google OAuth URL requesting Meet scopes")
    message_detail: Optional[str] = Field(None, description="Informational message or error description")
    invitation: Optional[MeetingInvitationRead] = None
    message: Optional[MessageRead] = None


class GoogleMeetCallbackRequest(BaseModel):
    code: Optional[str] = Field(None, description="Authorization code returned by Google")
    state: Optional[str] = Field(None, description="Signed OAuth state returned by Google")
    redirect_uri: Optional[str] = Field(None, description="Redirect URI used in initial request")

