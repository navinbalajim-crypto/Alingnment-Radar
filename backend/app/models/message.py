"""Message entity model supporting text, shared links, and AI notices."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.conversation import Conversation
    from app.models.attachment import MessageAttachment
    from app.models.voice_transcript import VoiceTranscript


class Message(Base):
    """Persisted chat message entity with structured metadata and idempotency key."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), default="text", nullable=False)  # text, link_share, ai_alignment, ai_recommendation, attachment, voice_note, meeting_invitation
    msg_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    client_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    is_deleted_for_everyone: Mapped[bool] = mapped_column(default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reply_to_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("messages.id", ondelete="SET NULL"), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    sender: Mapped[Optional["User"]] = relationship("User", foreign_keys=[sender_id], back_populates="messages")
    deleted_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[deleted_by_id])
    reply_to: Mapped[Optional["Message"]] = relationship("Message", remote_side=[id], foreign_keys=[reply_to_message_id])
    attachments: Mapped[list["MessageAttachment"]] = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan")
    voice_transcript: Mapped[Optional["VoiceTranscript"]] = relationship("VoiceTranscript", back_populates="message", uselist=False, cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
        Index("ix_messages_conv_client", "conversation_id", "client_id"),
        Index(
            "uq_messages_sender_client",
            "conversation_id", "sender_id", "client_id",
            unique=True,
            sqlite_where=text("client_id IS NOT NULL"),
            postgresql_where=text("client_id IS NOT NULL"),
        ),
    )
