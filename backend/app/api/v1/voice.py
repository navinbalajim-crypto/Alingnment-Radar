"""Voice message endpoints under /api/v1/conversations/{conversation_id}/voice."""

import asyncio
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.db.base import utc_now
from app.db.session import get_db
from app.models.attachment import MessageAttachment
from app.models.message import Message
from app.models.user import User
from app.models.voice_transcript import VoiceTranscript
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.events import ServerMessageNewPayload
from app.schemas.voice import (
    VoiceNoteCreateResponse,
    VoiceTranscriptRead,
    VoiceTranslationRequest,
    VoiceTranslationResponse,
)
from app.services.attachment_service import AttachmentService
from app.services.conversation_service import ConversationService
from app.services.speech_service import SpeechService
from app.sockets.server import sio

router = APIRouter(tags=["Voice Messages"])


@router.post(
    "/conversations/{conversation_id}/voice",
    response_model=VoiceNoteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_voice_note(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    duration: float = Form(...),
    client_id: Optional[str] = Form(None),
    reply_to_message_id: Optional[uuid.UUID] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an audio recording as an Instagram-style voice note.
    Stores audio securely on disk, persists message + VoiceTranscript, delivers message via Socket.IO,
    and schedules background transcription.
    """
    if duration <= 0:
        raise BadRequestError("Recording duration must be greater than zero.")

    # Save audio file through attachment service
    attachment_service = AttachmentService(db)
    duration_label = f"Voice note ({int(duration)}s)" if duration else "Voice note"
    message, attachment = await attachment_service.save_attachment(
        conversation_id=conversation_id,
        uploader_id=current_user.id,
        upload_file=file,
        caption=duration_label,
        client_id=client_id,
        reply_to_message_id=reply_to_message_id,
        message_type="voice_note",
        msg_metadata={
            "is_voice_note": True,
            "duration_seconds": duration,
        },
    )

    # Create initial VoiceTranscript in uploaded state
    transcript = VoiceTranscript(
        message_id=message.id,
        attachment_id=attachment.id,
        duration_seconds=duration,
        transcription_status="uploaded",
        translations={},
        provider_metadata={},
    )
    db.add(transcript)
    await db.commit()

    # Re-fetch formatted MessageRead
    conv_service = ConversationService(db)
    fresh_message = await conv_service.message_repo.get_by_id(message.id)
    msg_read = conv_service._format_message_read(fresh_message or message)

    # Deliver voice note to conversation room via Socket.IO immediately
    room_name = f"conversation:{conversation_id}"
    new_event = ServerMessageNewPayload(message=msg_read)
    await sio.emit("message:new", new_event.model_dump(mode="json"), room=room_name)

    # Schedule non-blocking background transcription
    asyncio.create_task(
        SpeechService.run_transcription_background(
            message_id=message.id,
            conversation_id=conversation_id,
            audio_path_str=attachment.storage_path,
        )
    )

    return VoiceNoteCreateResponse(
        message=msg_read,
        transcript=VoiceTranscriptRead.model_validate(transcript),
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/translate",
    response_model=VoiceTranslationResponse,
    status_code=status.HTTP_200_OK,
)
async def translate_voice_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    request: VoiceTranslationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Translate a voice note transcript to a selected supported target language."""
    speech_service = SpeechService(db)
    return await speech_service.translate_voice_transcript(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=current_user.id,
        target_language=request.target_language,
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/retry-transcription",
    response_model=VoiceTranscriptRead,
    status_code=status.HTTP_200_OK,
)
async def retry_transcription(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retry transcription for a voice note whose transcription failed or was pending consent."""
    conv_repo = ConversationRepository(db)
    is_member = await conv_repo.is_member(conversation_id, current_user.id)
    if not is_member:
        raise ForbiddenError("You are not a member of this conversation.")

    # The message must belong to the conversation the caller is a member of.
    stmt = (
        select(VoiceTranscript)
        .join(Message, Message.id == VoiceTranscript.message_id)
        .where(VoiceTranscript.message_id == message_id, Message.conversation_id == conversation_id)
        .options(selectinload(VoiceTranscript.attachment))
    )
    result = await db.execute(stmt)
    transcript = result.scalar_one_or_none()
    if not transcript or not transcript.attachment:
        raise NotFoundError("Voice note or audio attachment not found.")

    transcript.transcription_status = "queued"
    transcript.error_message = None
    transcript.updated_at = utc_now()
    await db.commit()

    asyncio.create_task(
        SpeechService.run_transcription_background(
            message_id=message_id,
            conversation_id=conversation_id,
            audio_path_str=transcript.attachment.storage_path,
        )
    )

    return VoiceTranscriptRead.model_validate(transcript)
