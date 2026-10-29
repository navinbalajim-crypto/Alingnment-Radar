"""Conversation schemas for direct chats and channel listing."""

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.message import MessageRead
from app.schemas.user import UserPublic


class CreateDirectConversationRequest(BaseModel):
    username: str


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_group: bool
    title: Optional[str] = None
    avatar_url: Optional[str] = None
    other_participant: Optional[UserPublic] = None
    last_message: Optional[MessageRead] = None
    member_count: int
    updated_at: datetime


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_group: bool
    title: Optional[str] = None
    created_by_id: Optional[uuid.UUID] = None
    members: List[UserPublic]
    created_at: datetime
    updated_at: datetime
