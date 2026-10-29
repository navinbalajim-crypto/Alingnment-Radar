"""Conversation service for direct chats, sidebar feeds, and message persistence."""

import uuid
from datetime import datetime
from typing import List, Optional, Set, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.models.conversation import Conversation
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.schemas.conversation import ConversationDetail, ConversationSummary
from app.schemas.message import AttachmentRead, MessageCreate, MessageHistoryResponse, MessageRead, ReplyToPreview
from app.schemas.user import UserPublic


class ConversationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)
        self.user_repo = UserRepository(session)

    async def get_or_create_direct_conversation(
        self, current_user_id: uuid.UUID, target_username: str
    ) -> ConversationSummary:
        target_user = await self.user_repo.get_by_username(target_username)
        if not target_user:
            raise NotFoundError(f"User '{target_username}' not found.")

        if target_user.id == current_user_id:
            raise BadRequestError("Cannot create a direct conversation with yourself.")

        # Check existing direct conversation
        conversation = await self.conv_repo.get_direct_conversation(
            user_a_id=current_user_id,
            user_b_id=target_user.id,
        )

        if not conversation:
            try:
                conversation = await self.conv_repo.create_direct_conversation(
                    user_a_id=current_user_id,
                    user_b_id=target_user.id,
                )
            except IntegrityError:
                # Concurrent creation occurred; rollback transaction and fetch existing
                await self.session.rollback()
                conversation = await self.conv_repo.get_direct_conversation(
                    user_a_id=current_user_id,
                    user_b_id=target_user.id,
                )
                if not conversation:
                    raise

        return await self._format_conversation_summary(conversation, current_user_id)

    async def list_user_conversations(self, current_user_id: uuid.UUID) -> List[ConversationSummary]:
        conversations = await self.conv_repo.get_user_conversations(current_user_id)
        summaries: List[ConversationSummary] = []
        for conv in conversations:
            summary = await self._format_conversation_summary(conv, current_user_id)
            summaries.append(summary)
        return summaries

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> MessageHistoryResponse:
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        messages = await self.message_repo.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit + 1,  # Fetch one extra to know if more exist
            before=before,
            user_id=user_id,
        )

        has_more = len(messages) > limit
        if has_more:
            messages = messages[1:]  # Drop oldest extra

        parent_ids = [
            m.reply_to_message_id
            for m in messages
            if getattr(m, "reply_to_message_id", None) is not None
        ]
        deleted_parent_ids = (
            await self.message_repo.get_user_deleted_message_ids(user_id, parent_ids)
            if parent_ids
            else set()
        )

        read_messages = [
            self._format_message_read(m, user_id=user_id, deleted_parent_ids=deleted_parent_ids)
            for m in messages
        ]
        next_cursor = read_messages[0].created_at.isoformat() if has_more and read_messages else None

        return MessageHistoryResponse(
            messages=read_messages,
            next_cursor=next_cursor,
            has_more=has_more,
            total_returned=len(read_messages),
        )

    async def save_message(
        self,
        conversation_id: uuid.UUID,
        sender_id: uuid.UUID,
        message_in: MessageCreate,
    ) -> MessageRead:
        is_member = await self.conv_repo.is_member(conversation_id, sender_id)
        if not is_member:
            raise ForbiddenError("You are not authorized to post in this conversation.")

        if message_in.reply_to_message_id:
            parent = await self.message_repo.get_by_id(message_in.reply_to_message_id)
            if not parent or parent.conversation_id != conversation_id:
                raise BadRequestError("Quoted message does not exist or belongs to another conversation.")

        # Check client idempotency key if provided
        if message_in.client_id:
            existing = await self.message_repo.get_by_client_id(
                conversation_id=conversation_id,
                client_id=message_in.client_id,
                sender_id=sender_id,
            )
            if existing:
                return self._format_message_read(existing)

        try:
            # Savepoint + unique index (conversation, sender, client_id): concurrent replays of the same
            # client message collapse to one row; the losers return the winner's message.
            async with self.session.begin_nested():
                message = await self.message_repo.create_message(
                    conversation_id=conversation_id,
                    sender_id=sender_id,
                    content=message_in.content,
                    message_type=message_in.message_type,
                    msg_metadata=message_in.msg_metadata,
                    client_id=message_in.client_id,
                    reply_to_message_id=message_in.reply_to_message_id,
                )
        except IntegrityError:
            winner = await self.message_repo.get_by_client_id(
                conversation_id=conversation_id, client_id=message_in.client_id or "", sender_id=sender_id
            )
            if winner is None:
                raise
            return self._format_message_read(winner)

        await self.conv_repo.touch(conversation_id)
        return self._format_message_read(message)

    async def delete_message(
        self,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        delete_type: str = "me",
    ) -> Tuple[str, MessageRead]:
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        message = await self.message_repo.get_by_id(message_id)
        if not message or message.conversation_id != conversation_id:
            raise NotFoundError("Message not found in this conversation.")

        if delete_type == "everyone":
            is_author = message.sender_id == user_id
            is_group_admin = False
            conv = await self.conv_repo.get_by_id(conversation_id)
            if conv and conv.is_group:
                for member in conv.members:
                    if member.user_id == user_id and getattr(member, "role", "member") == "admin":
                        is_group_admin = True
                        break

            if not is_author and not is_group_admin:
                raise ForbiddenError("You are not authorized to unsend this message for everyone.")

            updated = await self.message_repo.unsend_for_everyone(message, deleted_by_id=user_id)
            from app.services.context_graph_service import ContextGraphService
            await ContextGraphService(self.session).handle_message_deletion(conversation_id, message_id)
            return "everyone", self._format_message_read(updated)
        else:
            await self.message_repo.delete_for_me(message_id, user_id=user_id)
            return "me", self._format_message_read(message)

    async def _format_conversation_summary(
        self, conv: Conversation, current_user_id: uuid.UUID
    ) -> ConversationSummary:
        other_user = None
        if not conv.is_group:
            for member in conv.members:
                if member.user_id != current_user_id and member.user:
                    other_user = UserPublic.model_validate(member.user)
                    break

        last_message = await self.message_repo.get_last_message(conv.id, user_id=current_user_id)
        last_msg_read = self._format_message_read(last_message) if last_message else None

        return ConversationSummary(
            id=conv.id,
            is_group=conv.is_group,
            title=conv.title if conv.is_group else (other_user.username if other_user else "Direct Chat"),
            avatar_url=conv.avatar_url if conv.is_group else None,
            other_participant=other_user,
            last_message=last_msg_read,
            member_count=len(conv.members),
            updated_at=conv.updated_at,
        )

    def _format_message_read(
        self,
        m,
        user_id: Optional[uuid.UUID] = None,
        deleted_parent_ids: Optional[Set[uuid.UUID]] = None,
    ) -> MessageRead:
        sender_username = m.sender.username if m.sender else None
        is_deleted = getattr(m, "is_deleted_for_everyone", False)
        content = "This message was deleted." if is_deleted else m.content

        attachments = (
            []
            if is_deleted
            else [
                AttachmentRead(
                    id=att.id,
                    message_id=att.message_id,
                    conversation_id=att.conversation_id,
                    uploader_id=att.uploader_id,
                    original_filename=att.original_filename,
                    content_type=att.content_type,
                    file_size=att.file_size,
                    created_at=att.created_at,
                )
                for att in (getattr(m, "attachments", []) or [])
            ]
        )

        reply_to_preview = None
        if getattr(m, "reply_to_message_id", None) and getattr(m, "reply_to", None):
            parent = m.reply_to
            parent_deleted_everyone = getattr(parent, "is_deleted_for_everyone", False)
            parent_deleted_for_user = (
                parent.id in deleted_parent_ids if deleted_parent_ids else False
            )
            parent_is_deleted = parent_deleted_everyone or parent_deleted_for_user
            parent_sender = parent.sender.username if parent.sender else None
            parent_content = (
                "This message was deleted."
                if parent_is_deleted
                else (parent.content[:200] if parent.content else "")
            )
            parent_has_attachment = (
                bool(getattr(parent, "attachments", None)) and not parent_is_deleted
            )
            reply_to_preview = ReplyToPreview(
                id=parent.id,
                sender_id=parent.sender_id,
                sender_username=parent_sender,
                content=parent_content,
                message_type=parent.message_type,
                is_deleted_for_everyone=parent_deleted_everyone,
                has_attachment=parent_has_attachment,
            )

        voice_transcript_data = None
        if not is_deleted and getattr(m, "voice_transcript", None):
            from app.schemas.voice import VoiceTranscriptRead
            voice_transcript_data = VoiceTranscriptRead.model_validate(m.voice_transcript)

        return MessageRead(
            id=m.id,
            conversation_id=m.conversation_id,
            sender_id=m.sender_id,
            sender_username=sender_username,
            content=content,
            message_type=m.message_type,
            msg_metadata=m.msg_metadata or {},
            client_id=m.client_id,
            created_at=m.created_at,
            is_deleted_for_everyone=is_deleted,
            deleted_at=getattr(m, "deleted_at", None),
            attachments=attachments,
            reply_to_message_id=getattr(m, "reply_to_message_id", None),
            reply_to=reply_to_preview,
            voice_transcript=voice_transcript_data,
        )
