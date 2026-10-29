"""GmailNotification entity model for in-app Gmail notification alerts."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class GmailNotification(Base):
    """Stores minimal metadata for detected Gmail messages alerting the user."""

    __tablename__ = "gmail_notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="gmail_notifications")

    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_gmail_notifications_user_message"),
        Index("ix_gmail_notifications_user_created", "user_id", "created_at"),
        Index("ix_gmail_notifications_user_unread", "user_id", "is_read"),
    )

    def __repr__(self) -> str:
        return f"<GmailNotification id={self.id} user_id={self.user_id} msg_id={self.gmail_message_id}>"
