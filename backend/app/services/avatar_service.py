"""Profile picture (avatar) upload and retrieval for both personal user avatars and group
display pictures. Both share the same validation conventions as attachment uploads:
extension allowlist, magic-byte signature check, and a server-controlled filename (never
derived from user input) -- and are stored in their own directories so a group's image can
never collide with, or be confused for, a user's personal avatar."""

import time
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.models.conversation import Conversation
from app.models.user import User
from app.services.attachment_service import _validate_magic_bytes

MAX_AVATAR_SIZE = 3 * 1024 * 1024  # 3 MB
CHUNK_SIZE = 64 * 1024

ALLOWED_AVATAR_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
AVATAR_DIR = _UPLOADS_ROOT / "avatars"
GROUP_AVATAR_DIR = _UPLOADS_ROOT / "group_avatars"


async def _validate_and_store(directory: Path, filename_stem: str, upload_file: UploadFile) -> Tuple[Path, Path, str]:
    """Shared validation + atomic write used by both personal and group avatars. Returns
    (target_path, ext, content_type). Raises BadRequestError on any invalid input, writing
    only to a temp file so an existing image is never touched by a failed upload."""
    directory.mkdir(parents=True, exist_ok=True)
    original_name = Path(upload_file.filename or "").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        raise BadRequestError("Unsupported image type. Allowed formats: JPEG, PNG, WebP, GIF.")

    # Filename is derived solely from the caller-supplied entity id and the validated
    # extension, never from client input, so it cannot path-traverse or collide.
    target_path = directory / f"{filename_stem}{ext}"
    tmp_path = directory / f"{filename_stem}{ext}.tmp"

    total_bytes = 0
    first_chunk = True
    try:
        with open(tmp_path, "wb") as f:
            while True:
                chunk_bytes = await upload_file.read(CHUNK_SIZE)
                if not chunk_bytes:
                    break
                total_bytes += len(chunk_bytes)
                if total_bytes > MAX_AVATAR_SIZE:
                    raise BadRequestError(f"Image exceeds the 3 MB limit ({total_bytes / (1024 * 1024):.2f} MB).")
                if first_chunk:
                    first_chunk = False
                    if not _validate_magic_bytes(chunk_bytes[:64], ext):
                        raise BadRequestError("File signature does not match the expected image format.")
                f.write(chunk_bytes)
        if total_bytes == 0:
            raise BadRequestError("Cannot upload an empty file.")
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return target_path, tmp_path, ext


def _remove_existing_files(directory: Path, filename_stem: str, keep_ext: Optional[str] = None) -> None:
    for existing_ext in ALLOWED_AVATAR_EXTENSIONS:
        if existing_ext == keep_ext:
            continue
        candidate = directory / f"{filename_stem}{existing_ext}"
        if candidate.exists():
            candidate.unlink(missing_ok=True)


def _get_avatar_file(directory: Path, filename_stem: str) -> Optional[Tuple[Path, str]]:
    for ext, content_type in ALLOWED_AVATAR_EXTENSIONS.items():
        candidate = directory / f"{filename_stem}{ext}"
        if candidate.exists():
            return candidate, content_type
    return None


class AvatarService:
    def __init__(self, session: AsyncSession):
        self.session = session
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        GROUP_AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Personal (user) avatars -------------------------------------------------

    async def set_avatar(self, user: User, upload_file: UploadFile) -> str:
        """Validate and store a new avatar image for `user`, replacing any previous one.
        Returns the public URL to fetch it. Raises BadRequestError on invalid input,
        leaving the user's existing avatar untouched."""
        target_path, tmp_path, ext = await _validate_and_store(AVATAR_DIR, user.id.hex, upload_file)

        # Only now that the new file is fully validated do we touch the previous avatar.
        _remove_existing_files(AVATAR_DIR, user.id.hex, keep_ext=ext)
        tmp_path.replace(target_path)

        # A version query param makes each re-upload a distinct URL, so browsers (and any
        # other participant's client) never serve a stale cached image after a replace.
        avatar_url = f"/api/v1/users/{user.id}/avatar?v={int(time.time())}"
        user.avatar_url = avatar_url
        await self.session.flush()
        return avatar_url

    @staticmethod
    def get_avatar_file(user_id: uuid.UUID) -> Optional[Tuple[Path, str]]:
        """Return (file_path, content_type) for this user's stored avatar, if any."""
        return _get_avatar_file(AVATAR_DIR, user_id.hex)

    # ---- Group display pictures ---------------------------------------------------
    # Stored in a separate directory, keyed by the group's own conversation id, so a
    # group's image can never collide with a user's personal avatar filename, and
    # changing one group's picture can never touch another group's or a user's own.

    async def set_group_avatar(self, conversation: Conversation, upload_file: UploadFile) -> str:
        """Validate and store a new display picture for `conversation` (a group), replacing
        any previous one. Raises BadRequestError on invalid input, leaving the group's
        existing picture untouched."""
        target_path, tmp_path, ext = await _validate_and_store(GROUP_AVATAR_DIR, conversation.id.hex, upload_file)

        _remove_existing_files(GROUP_AVATAR_DIR, conversation.id.hex, keep_ext=ext)
        tmp_path.replace(target_path)

        avatar_url = f"/api/v1/groups/{conversation.id}/avatar?v={int(time.time())}"
        conversation.avatar_url = avatar_url
        await self.session.flush()
        return avatar_url

    @staticmethod
    def remove_group_avatar(conversation: Conversation) -> None:
        """Delete the group's stored image file(s) and clear its avatar_url, restoring the
        default group avatar. A group with no custom picture is a no-op."""
        _remove_existing_files(GROUP_AVATAR_DIR, conversation.id.hex, keep_ext=None)
        conversation.avatar_url = None

    @staticmethod
    def get_group_avatar_file(conversation_id: uuid.UUID) -> Optional[Tuple[Path, str]]:
        """Return (file_path, content_type) for this group's stored picture, if any."""
        return _get_avatar_file(GROUP_AVATAR_DIR, conversation_id.hex)
