"""UserMessageDeletion entity model for per-user message visibility deletion."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


class UserMessageDeletion(Base):
    """Tracks messages deleted for an individual user ('Delete for me')."""

    __tablename__ = "user_message_deletions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
    message: Mapped["Message"] = relationship("Message")

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_user_message_deletions"),
        Index("ix_user_message_deletions_user_msg", "user_id", "message_id"),
    )
