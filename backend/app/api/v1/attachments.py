"""Attachment upload and download endpoints under /api/v1/conversations/{conversation_id}/attachments."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.events import ServerMessageNewPayload
from app.schemas.message import MessageRead
from app.services.attachment_service import AttachmentService
from app.services.conversation_service import ConversationService
from app.sockets.server import sio

router = APIRouter(prefix="/conversations/{conversation_id}/attachments", tags=["Attachments"])


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    reply_to_message_id: Optional[uuid.UUID] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an image or document (up to 10 MB) into a direct or group conversation.
    Enforces strict size, signature, and membership verification.
    """
    service = AttachmentService(db)
    message, attachment = await service.save_attachment(
        conversation_id=conversation_id,
        uploader_id=current_user.id,
        upload_file=file,
        caption=caption,
        client_id=client_id,
        reply_to_message_id=reply_to_message_id,
    )
    await db.commit()

    # Re-fetch formatted MessageRead
    conv_service = ConversationService(db)
    fresh_message = await conv_service.message_repo.get_by_id(message.id)
    msg_read = conv_service._format_message_read(fresh_message or message)

    # Broadcast message:new to room
    room_name = f"conversation:{conversation_id}"
    new_event = ServerMessageNewPayload(message=msg_read)
    await sio.emit("message:new", new_event.model_dump(mode="json"), room=room_name)

    return msg_read


@router.get("/{attachment_id}")
async def download_attachment(
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download or view a protected attachment after strictly verifying user membership.
    Access is revoked if the message was deleted for everyone.
    """
    service = AttachmentService(db)
    file_path, filename, content_type = await service.get_attachment_for_download(
        conversation_id=conversation_id,
        attachment_id=attachment_id,
        user_id=current_user.id,
    )

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=filename,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
