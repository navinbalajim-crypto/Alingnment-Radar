"""VoiceTranscript entity model for voice note speech recognition and multilingual translation."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.attachment import MessageAttachment


class VoiceTranscript(Base):
    """Persisted speech recognition transcript and multilingual translations for voice notes."""

    __tablename__ = "voice_transcripts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    attachment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("message_attachments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    transcription_status: Mapped[str] = mapped_column(
        String(50), default="uploaded", nullable=False
    )  # uploaded, queued, processing, completed, failed, consent_required
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provider_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="voice_transcript")
    attachment: Mapped[Optional["MessageAttachment"]] = relationship("MessageAttachment")

    def __repr__(self) -> str:
        return f"<VoiceTranscript id={self.id} message_id={self.message_id} status={self.transcription_status}>"
