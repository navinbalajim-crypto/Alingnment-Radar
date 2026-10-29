"""Message repository for chat message storage and retrieval."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.message import Message
from app.models.message_deletion import UserMessageDeletion
from app.db.base import utc_now


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_message(
        self,
        conversation_id: uuid.UUID,
        sender_id: Optional[uuid.UUID],
        content: str,
        message_type: str = "text",
        msg_metadata: Optional[Dict[str, Any]] = None,
        client_id: Optional[str] = None,
        reply_to_message_id: Optional[uuid.UUID] = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            msg_metadata=msg_metadata or {},
            client_id=client_id,
            reply_to_message_id=reply_to_message_id,
        )
        self.session.add(message)
        await self.session.flush()
        # Eagerly load sender and attachments
        return await self.get_by_id(message.id)  # type: ignore

    async def get_by_id(self, message_id: uuid.UUID) -> Optional[Message]:
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.voice_transcript),
                selectinload(Message.reply_to).selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.attachments),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_client_id(
        self, conversation_id: uuid.UUID, client_id: str, sender_id: Optional[uuid.UUID] = None
    ) -> Optional[Message]:
        """Idempotency lookup. Scoped to the sender so one member's key can never resolve to another's message."""
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.client_id == client_id,
            )
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.voice_transcript),
                selectinload(Message.reply_to).selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.attachments),
            )
            .limit(1)
        )
        if sender_id is not None:
            stmt = stmt.where(Message.sender_id == sender_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        before: Optional[datetime] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.voice_transcript),
                selectinload(Message.reply_to).selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.attachments),
            )
        )
        if user_id is not None:
            stmt = stmt.where(
                ~Message.id.in_(
                    select(UserMessageDeletion.message_id).where(UserMessageDeletion.user_id == user_id)
                )
            )
        if before is not None:
            stmt = stmt.where(Message.created_at < before)

        stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        # Return in chronological order
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def get_recent_messages(
        self, conversation_id: uuid.UUID, limit: int = 30
    ) -> List[Message]:
        """Fetch the most recent messages in chronological order for AI analysis context."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.reply_to).selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.attachments),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def get_last_message(
        self, conversation_id: uuid.UUID, user_id: Optional[uuid.UUID] = None
    ) -> Optional[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.reply_to).selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.attachments),
            )
        )
        if user_id is not None:
            stmt = stmt.where(
                ~Message.id.in_(
                    select(UserMessageDeletion.message_id).where(UserMessageDeletion.user_id == user_id)
                )
            )
        stmt = stmt.order_by(Message.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_for_me(self, message_id: uuid.UUID, user_id: uuid.UUID) -> UserMessageDeletion:
        """Record per-user message deletion ('Delete for me')."""
        stmt = select(UserMessageDeletion).where(
            UserMessageDeletion.message_id == message_id,
            UserMessageDeletion.user_id == user_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing
        deletion = UserMessageDeletion(user_id=user_id, message_id=message_id)
        self.session.add(deletion)
        await self.session.flush()
        return deletion

    async def unsend_for_everyone(self, message: Message, deleted_by_id: uuid.UUID) -> Message:
        """Mark message as unsent/deleted for everyone."""
        message.is_deleted_for_everyone = True
        message.deleted_at = utc_now()
        message.deleted_by_id = deleted_by_id
        await self.session.flush()
        return message

    async def get_user_deleted_message_ids(
        self, user_id: uuid.UUID, message_ids: List[uuid.UUID]
    ) -> Set[uuid.UUID]:
        """Return the subset of message_ids that the given user has deleted for themselves."""
        if not message_ids:
            return set()
        stmt = select(UserMessageDeletion.message_id).where(
            UserMessageDeletion.user_id == user_id,
            UserMessageDeletion.message_id.in_(message_ids),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())
