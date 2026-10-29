"""Voice message transcription and multilingual translation schemas."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.message import MessageRead

SUPPORTED_TRANSLATION_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "zh": "Chinese",
    "ja": "Japanese",
    "ar": "Arabic",
    "pt": "Portuguese",
    "ru": "Russian",
    "it": "Italian",
    "ko": "Korean",
    "nl": "Dutch",
    "tr": "Turkish",
}


class VoiceTranscriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    attachment_id: Optional[uuid.UUID] = None
    duration_seconds: Optional[float] = None
    source_language: Optional[str] = None
    transcript_text: Optional[str] = None
    transcript_version: int = 1
    transcription_status: str  # uploaded, queued, processing, completed, failed, consent_required
    error_message: Optional[str] = None
    translations: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class VoiceTranslationRequest(BaseModel):
    target_language: str = Field(..., min_length=2, max_length=10, description="Target language code (e.g., 'es', 'fr', 'hi')")


class VoiceTranslationResponse(BaseModel):
    message_id: uuid.UUID
    source_language: str
    target_language: str
    translated_text: str
    provider: str
    cached: bool = False


class VoiceNoteCreateResponse(BaseModel):
    message: MessageRead
    transcript: Optional[VoiceTranscriptRead] = None
