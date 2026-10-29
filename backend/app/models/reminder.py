"""TaskReminder and UserNotification entity models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User


class TaskReminder(Base):
    """Scheduled task reminder extracted from conversation or created manually."""

    __tablename__ = "task_reminders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    responsible_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    advance_reminder_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    advance_scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)  # pending, completed, cancelled, dismissed
    advance_delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    due_delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    responsible_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[responsible_user_id])

    __table_args__ = (
        Index("ix_task_reminders_status_due", "status", "due_at"),
        Index("ix_task_reminders_advance", "status", "advance_delivered", "advance_scheduled_at"),
        Index("ix_task_reminders_due_poll", "status", "due_delivered", "due_at"),
    )


class UserNotification(Base):
    """In-app persistent notification delivered to a user."""

    __tablename__ = "user_notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    reminder_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("task_reminders.id", ondelete="CASCADE"), nullable=True)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)

    type: Mapped[str] = mapped_column(String(50), default="task_reminder", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    reminder: Mapped[Optional["TaskReminder"]] = relationship("TaskReminder")
    conversation: Mapped[Optional["Conversation"]] = relationship("Conversation")

    __table_args__ = (
        Index("ix_user_notifications_user_unread", "user_id", "is_read", "created_at"),
    )
