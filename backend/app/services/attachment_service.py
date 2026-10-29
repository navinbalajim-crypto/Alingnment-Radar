"""Attachment service for secure image and document uploads up to 10 MB."""

import os
import re
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models.attachment import MessageAttachment
from app.models.message import Message
from app.repositories.conversation_repo import ConversationRepository

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB strict limit
CHUNK_SIZE = 64 * 1024  # 64 KB

ALLOWED_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}

DISALLOWED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".bin", ".js", ".py", ".vbs", ".ps1", ".msi", ".dll", ".so", ".php"
}

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


def _sanitize_filename(name: str) -> str:
    """Strip path elements and unsafe characters from display filename."""
    base = Path(name).name
    cleaned = re.sub(r"[^\w\s\.-]", "_", base).strip()
    return cleaned[:150] or "attachment"


def _validate_magic_bytes(header: bytes, ext: str) -> bool:
    """Validate initial file signature against expected extension."""
    if ext in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".gif":
        return header.startswith(b"GIF87a") or header.startswith(b"GIF89a")
    if ext == ".pdf":
        return header.startswith(b"%PDF-")
    if ext == ".webp":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if ext == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if ext == ".ogg":
        return header.startswith(b"OggS")
    if ext == ".wav":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if ext == ".mp3":
        return header.startswith(b"ID3") or header.startswith(b"\xff\xfb") or header.startswith(b"\xff\xf3") or header.startswith(b"\xff\xf2")
    if ext == ".m4a":
        return b"ftyp" in header[:16]
    if ext == ".txt":
        # Disallow embedded null bytes which indicate binary/executable content
        return b"\x00" not in header
    # Office documents (OLE or ZIP-based OpenXML)
    if ext in {".docx", ".xlsx"}:
        return header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06")
    if ext in {".doc", ".xls"}:
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or header.startswith(b"PK\x03\x04")
    return True


class AttachmentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async def save_attachment(
        self,
        conversation_id: uuid.UUID,
        uploader_id: uuid.UUID,
        upload_file: UploadFile,
        caption: Optional[str] = None,
        client_id: Optional[str] = None,
        reply_to_message_id: Optional[uuid.UUID] = None,
        message_type: str = "attachment",
        msg_metadata: Optional[dict] = None,
    ) -> Tuple[Message, MessageAttachment]:
        """Validate, stream-save to disk, and persist Message + MessageAttachment."""
        is_member = await self.conv_repo.is_member(conversation_id, uploader_id)
        if not is_member:
            raise ForbiddenError("You are not authorized to post in this conversation.")

        if reply_to_message_id:
            parent = await self.session.get(Message, reply_to_message_id)
            if not parent or parent.conversation_id != conversation_id:
                raise BadRequestError("Quoted message does not exist or belongs to another conversation.")

        original_filename = _sanitize_filename(upload_file.filename or "file")
        ext = Path(original_filename).suffix.lower()

        if ext in DISALLOWED_EXTENSIONS or ext not in ALLOWED_EXTENSIONS:
            raise BadRequestError(
                f"File type '{ext}' is not supported. Supported: images (JPEG, PNG, WebP, GIF), documents (PDF, TXT, DOC, DOCX, XLS, XLSX), and audio (WebM, OGG, WAV, MP3, M4A)."
            )

        content_type = ALLOWED_EXTENSIONS[ext]
        storage_filename = f"{uuid.uuid4().hex}{ext}"
        storage_path = UPLOAD_DIR / storage_filename

        total_bytes = 0
        first_chunk = True

        try:
            with open(storage_path, "wb") as f:
                while True:
                    chunk = await upload_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_FILE_SIZE:
                        raise BadRequestError(
                            f"File size exceeds 10 MB limit ({total_bytes / (1024 * 1024):.2f} MB)."
                        )
                    if first_chunk:
                        first_chunk = False
                        if not _validate_magic_bytes(chunk[:64], ext):
                            raise BadRequestError(
                                f"File signature does not match expected format for extension '{ext}'."
                            )
                    f.write(chunk)
        except Exception:
            if storage_path.exists():
                try:
                    storage_path.unlink()
                except OSError:
                    pass
            raise

        if total_bytes == 0:
            if storage_path.exists():
                storage_path.unlink()
            raise BadRequestError("Cannot upload an empty file.")

        msg_content = (caption.strip() if caption and caption.strip() else original_filename)
        attachment_id = uuid.uuid4()

        final_metadata = {
            "attachment_id": str(attachment_id),
            "original_filename": original_filename,
            "content_type": content_type,
            "file_size": total_bytes,
        }
        if msg_metadata:
            final_metadata.update(msg_metadata)

        message = Message(
            conversation_id=conversation_id,
            sender_id=uploader_id,
            content=msg_content,
            message_type=message_type,
            msg_metadata=final_metadata,
            client_id=client_id,
            reply_to_message_id=reply_to_message_id,
        )
        self.session.add(message)
        await self.session.flush()

        attachment = MessageAttachment(
            id=attachment_id,
            message_id=message.id,
            conversation_id=conversation_id,
            uploader_id=uploader_id,
            original_filename=original_filename,
            content_type=content_type,
            file_size=total_bytes,
            storage_path=str(storage_path),
        )
        self.session.add(attachment)
        await self.session.flush()

        await self.conv_repo.touch(conversation_id)
        return message, attachment

    async def get_attachment_for_download(
        self,
        conversation_id: uuid.UUID,
        attachment_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Tuple[Path, str, str]:
        """
        Verify membership, ensure message not deleted for everyone, and return (filepath, filename, content_type).
        """
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        stmt = (
            select(MessageAttachment)
            .where(
                MessageAttachment.id == attachment_id,
                MessageAttachment.conversation_id == conversation_id,
            )
            .options(selectinload(MessageAttachment.message))
        )
        result = await self.session.execute(stmt)
        attachment = result.scalar_one_or_none()

        if not attachment:
            raise NotFoundError("Attachment not found.")

        if attachment.message and attachment.message.is_deleted_for_everyone:
            raise NotFoundError("Attachment is no longer available because the message was deleted.")

        file_path = Path(attachment.storage_path).resolve()
        try:
            if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
                raise NotFoundError("Invalid attachment storage path.")
        except (ValueError, AttributeError):
            raise NotFoundError("Invalid attachment storage path.")

        if not file_path.exists():
            raise NotFoundError("Attachment file not found on server.")

        return file_path, attachment.original_filename, attachment.content_type
