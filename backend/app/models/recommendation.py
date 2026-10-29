"""Contextual Recommendation entity model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.message import Message
    from app.models.user import User


class RecommendationItem(Base):
    """External recommendation item (YouTube, Spotify, Tavily) linked to conversation."""

    __tablename__ = "recommendation_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    triggered_by_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # youtube, spotify, tavily
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # music, cricket, web, other
    published_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extra_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_shared_in_chat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    dismissed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="recommendations")
    triggered_by_message: Mapped[Optional["Message"]] = relationship("Message")
    dismissed_by: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_recommendation_conv_dismissed", "conversation_id", "is_dismissed"),
    )
