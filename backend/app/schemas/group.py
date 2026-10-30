"""Group and membership management schemas."""

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateGroupRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150, description="Group title")
    initial_member_usernames: Optional[List[str]] = Field(default=None, description="Optional list of usernames to invite immediately")


class GroupMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime


class GroupDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    avatar_url: Optional[str] = None
    created_by_id: Optional[uuid.UUID] = None
    members: List[GroupMemberResponse]
    created_at: datetime
    updated_at: datetime


class CreateInvitationRequest(BaseModel):
    max_uses: Optional[int] = Field(None, ge=1, le=1000, description="Maximum allowed uses, or null for unlimited")
    expires_in_days: int = Field(7, ge=1, le=90, description="Invitation expiration in days")


class InvitationResponse(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    invitation_url: str
    token: str
    max_uses: Optional[int]
    uses_count: int
    expires_at: datetime
    created_at: datetime
