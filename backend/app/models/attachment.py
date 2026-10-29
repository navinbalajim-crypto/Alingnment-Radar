"""MessageAttachment entity model for images and documents."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.conversation import Conversation
    from app.models.user import User


class MessageAttachment(Base):
    """File or image attachment linked to a chat message."""

    __tablename__ = "message_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    uploader_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="attachments")
    conversation: Mapped["Conversation"] = relationship("Conversation")
    uploader: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_message_attachments_conv", "conversation_id"),
        Index("ix_message_attachments_msg", "message_id"),
    )
