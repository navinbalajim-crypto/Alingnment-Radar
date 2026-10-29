"""MeetingInvitation entity model for Google Meet and video conference invitations."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.conversation import Conversation
    from app.models.message import Message


class MeetingInvitation(Base):
    """Persisted meeting space or video conference invitation."""

    __tablename__ = "meeting_invitations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    creator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), index=True, nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), default="google_meet", nullable=False)
    meeting_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    meeting_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    space_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)  # active, ended, cancelled
    client_token: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation")
    creator: Mapped[Optional["User"]] = relationship("User")
    message: Mapped[Optional["Message"]] = relationship("Message")

    __table_args__ = (
        Index("ix_meeting_invitations_conv_created", "conversation_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<MeetingInvitation id={self.id} provider={self.provider} uri={self.meeting_uri}>"
