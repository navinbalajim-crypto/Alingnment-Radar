"""User entity model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.session import RefreshSession
    from app.models.conversation import ConversationMember
    from app.models.message import Message
    from app.models.oauth_connection import OAuthConnection
    from app.models.user_contact import UserContact
    from app.models.gmail_notification import GmailNotification


class User(Base):
    """User account model with case-insensitive unique username."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Explicit opt-ins for sending *unsent* draft text to external services. Always default to off.
    ai_draft_analysis_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false(), nullable=False)
    ai_autocomplete_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false(), nullable=False)
    draft_recommendations_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    refresh_sessions: Mapped[List["RefreshSession"]] = relationship("RefreshSession", back_populates="user", cascade="all, delete-orphan")
    memberships: Mapped[List["ConversationMember"]] = relationship("ConversationMember", back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="sender", foreign_keys="[Message.sender_id]")
    oauth_connections: Mapped[List["OAuthConnection"]] = relationship("OAuthConnection", back_populates="user", cascade="all, delete-orphan")
    contacts: Mapped[List["UserContact"]] = relationship("UserContact", back_populates="user", cascade="all, delete-orphan")
    gmail_notifications: Mapped[List["GmailNotification"]] = relationship("GmailNotification", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_username_lower", func.lower(username), unique=True),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"
