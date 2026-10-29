"""Conversation and ConversationMember models supporting direct chats and groups."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.message import Message
    from app.models.invitation import GroupInvitation
    from app.models.alignment import AlignmentFinding
    from app.models.recommendation import RecommendationItem


class Conversation(Base):
    """Conversation entity supporting direct 1-to-1 chats and group channels."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Group display picture only; always null for direct conversations (they use the other
    # participant's personal avatar_url instead).
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # For direct 1-to-1 chats: sorted pair of user UUIDs ensures strict DB-level uniqueness
    direct_user_low_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True, index=True)
    direct_user_high_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    members: Mapped[List["ConversationMember"]] = relationship("ConversationMember", back_populates="conversation", cascade="all, delete-orphan")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    invitations: Mapped[List["GroupInvitation"]] = relationship("GroupInvitation", back_populates="group", cascade="all, delete-orphan")
    alignment_findings: Mapped[List["AlignmentFinding"]] = relationship("AlignmentFinding", back_populates="conversation", cascade="all, delete-orphan")
    recommendations: Mapped[List["RecommendationItem"]] = relationship("RecommendationItem", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("direct_user_low_id", "direct_user_high_id", name="uq_direct_conversation_user_pair"),
    )


class ConversationMember(Base):
    """Membership mapping of a user within a conversation."""

    __tablename__ = "conversation_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)  # "admin", "member"
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_member"),
        Index("ix_conversation_members_user_conv", "user_id", "conversation_id"),
    )
