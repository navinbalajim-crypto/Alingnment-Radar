"""Socket.IO real-time event schemas and payload contracts."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
from app.schemas.ai import AlignmentFindingResponse, RecommendationItemResponse
from app.schemas.message import MessageRead


class ClientJoinPayload(BaseModel):
    """Payload sent by client to join a conversation room."""
    conversation_id: uuid.UUID


class ClientSendMessagePayload(BaseModel):
    """Payload sent by client to send a chat message."""
    conversation_id: uuid.UUID
    content: str = Field(..., min_length=1, max_length=5000)
    message_type: str = Field("text", description="text, link_share, ai_alignment, ai_recommendation")
    msg_metadata: Dict[str, Any] = Field(default_factory=dict)
    client_id: Optional[str] = Field(None, max_length=64, description="Client idempotency key")
    reply_to_message_id: Optional[uuid.UUID] = Field(None, description="Optional parent message ID being replied to")

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty or contain only whitespace.")
        return v


class ServerMessageAckPayload(BaseModel):
    """Payload sent by server to acknowledge message receipt and DB persistence."""
    status: str = "ok"
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    client_id: Optional[str] = None
    created_at: datetime


class ServerMessageNewPayload(BaseModel):
    """Broadcast to conversation room when a new message is saved."""
    message: MessageRead


class ServerMessageErrorPayload(BaseModel):
    """Error notification sent to client on event failure."""
    code: str
    message: str
    client_id: Optional[str] = None


class ServerAiAlignmentPayload(BaseModel):
    """Broadcast to conversation room when an AI alignment finding is produced."""
    finding: AlignmentFindingResponse


class ServerAiRecommendationPayload(BaseModel):
    """Broadcast to conversation room when AI contextual recommendations are ready."""
    recommendation: RecommendationItemResponse


class GroupMemberJoinedPayload(BaseModel):
    """Broadcast to group room when a new member joins via invitation."""
    group_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str = "member"
    joined_at: datetime
