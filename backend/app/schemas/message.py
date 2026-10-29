"""Chat message schemas."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_MESSAGE_TYPES = {
    "text",
    "link_share",
    "ai_alignment",
    "ai_recommendation",
    "attachment",
    "meeting_invitation",
    "voice_note",
}


class ReplyToPreview(BaseModel):
    id: uuid.UUID
    sender_id: Optional[uuid.UUID] = None
    sender_username: Optional[str] = None
    content: str
    message_type: str = "text"
    is_deleted_for_everyone: bool = False
    has_attachment: bool = False


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    uploader_id: Optional[uuid.UUID] = None
    original_filename: str
    content_type: str
    file_size: int
    created_at: datetime


class MessageDeleteRequest(BaseModel):
    delete_type: str = Field("me", description="'me' for Delete for me, 'everyone' for Unsend for everyone")

    @field_validator("delete_type")
    @classmethod
    def validate_delete_type(cls, v: str) -> str:
        if v not in {"me", "everyone"}:
            raise ValueError("delete_type must be either 'me' or 'everyone'")
        return v


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000, description="Message text content")
    message_type: str = Field("text", description="Type of message: text, link_share, ai_alignment, ai_recommendation, attachment")
    msg_metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured message metadata")
    client_id: Optional[str] = Field(None, max_length=64, description="Client idempotency key")
    reply_to_message_id: Optional[uuid.UUID] = Field(None, description="Optional ID of parent message being replied to")

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty or contain only whitespace.")
        return v

    @field_validator("message_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ALLOWED_MESSAGE_TYPES:
            raise ValueError(f"message_type must be one of: {', '.join(sorted(ALLOWED_MESSAGE_TYPES))}")
        return v


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: Optional[uuid.UUID] = None
    sender_username: Optional[str] = None
    content: str
    message_type: str
    msg_metadata: Dict[str, Any]
    client_id: Optional[str] = None
    created_at: datetime
    is_deleted_for_everyone: bool = False
    deleted_at: Optional[datetime] = None
    attachments: List[AttachmentRead] = Field(default_factory=list)
    reply_to_message_id: Optional[uuid.UUID] = None
    reply_to: Optional[ReplyToPreview] = None
    voice_transcript: Optional[Any] = None


class MessageHistoryResponse(BaseModel):
    messages: List[MessageRead]
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_returned: int
