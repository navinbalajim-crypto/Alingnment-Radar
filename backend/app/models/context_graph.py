"""Live Conversation Context Graph entity models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User
    from app.models.message import Message


class ContextNode(Base):
    """
    Structured context item extracted from conversation.
    Captures tasks, commitments, responsible people, deadlines, status, questions, confirmations.
    """

    __tablename__ = "context_nodes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(50), default="task", nullable=False)  # task, commitment, question, confirmation, entity
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    responsible_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deadline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Contextual or explicit string, e.g. "tonight"
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, in_progress, completed, uncertain, cancelled
    evidence_message_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_updated_by_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation")
    responsible_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[responsible_user_id])
    last_updated_by_message: Mapped[Optional["Message"]] = relationship("Message", foreign_keys=[last_updated_by_message_id])

    __table_args__ = (
        Index("ix_context_nodes_conv_status", "conversation_id", "status"),
        Index("ix_context_nodes_conv_type", "conversation_id", "node_type"),
    )


class ContextInconsistency(Base):
    """
    Detected potential contradiction or status change between earlier intention/commitment
    and subsequent messages in the conversation.
    """

    __tablename__ = "context_inconsistencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    earlier_evidence_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    later_evidence_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    clarification_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="detected", nullable=False)  # detected, clarified, dismissed, resolved
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation")
    node: Mapped[Optional["ContextNode"]] = relationship("ContextNode")
    earlier_evidence_message: Mapped[Optional["Message"]] = relationship("Message", foreign_keys=[earlier_evidence_message_id])
    later_evidence_message: Mapped[Optional["Message"]] = relationship("Message", foreign_keys=[later_evidence_message_id])

    __table_args__ = (
        Index("ix_context_inconsistencies_conv_status", "conversation_id", "status"),
    )
