"""Conversation repository for direct chats, groups, and membership checks."""

import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db.base import utc_now
from app.models.conversation import Conversation, ConversationMember


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, conversation_id: uuid.UUID) -> Optional[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_direct_conversation(
        self, user_a_id: uuid.UUID, user_b_id: uuid.UUID
    ) -> Optional[Conversation]:
        low_id = min(user_a_id, user_b_id)
        high_id = max(user_a_id, user_b_id)
        stmt = (
            select(Conversation)
            .where(
                Conversation.direct_user_low_id == low_id,
                Conversation.direct_user_high_id == high_id,
                Conversation.is_group.is_(False),
            )
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_direct_conversation(
        self, user_a_id: uuid.UUID, user_b_id: uuid.UUID
    ) -> Conversation:
        low_id = min(user_a_id, user_b_id)
        high_id = max(user_a_id, user_b_id)

        conversation = Conversation(
            is_group=False,
            direct_user_low_id=low_id,
            direct_user_high_id=high_id,
        )
        self.session.add(conversation)
        await self.session.flush()

        # Add both users as members
        member_a = ConversationMember(conversation_id=conversation.id, user_id=user_a_id, role="member")
        member_b = ConversationMember(conversation_id=conversation.id, user_id=user_b_id, role="member")
        self.session.add_all([member_a, member_b])
        await self.session.flush()

        # Reload with relationships
        return await self.get_by_id(conversation.id)  # type: ignore

    async def create_group_conversation(
        self, title: str, creator_id: uuid.UUID, initial_member_ids: Optional[List[uuid.UUID]] = None
    ) -> Conversation:
        conversation = Conversation(
            is_group=True,
            title=title.strip(),
            created_by_id=creator_id,
        )
        self.session.add(conversation)
        await self.session.flush()

        # Add creator as admin
        admin_member = ConversationMember(
            conversation_id=conversation.id,
            user_id=creator_id,
            role="admin",
        )
        self.session.add(admin_member)

        # Add initial members
        if initial_member_ids:
            for uid in initial_member_ids:
                if uid != creator_id:
                    self.session.add(
                        ConversationMember(
                            conversation_id=conversation.id,
                            user_id=uid,
                            role="member",
                        )
                    )

        await self.session.flush()
        return await self.get_by_id(conversation.id)  # type: ignore

    async def get_user_conversations(self, user_id: uuid.UUID) -> List[Conversation]:
        stmt = (
            select(Conversation)
            .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
            .where(ConversationMember.user_id == user_id)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user),
            )
            .order_by(Conversation.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_members(
        self, conversation_id: uuid.UUID
    ) -> List[ConversationMember]:
        stmt = (
            select(ConversationMember)
            .where(ConversationMember.conversation_id == conversation_id)
            .options(selectinload(ConversationMember.user))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_member(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ConversationMember]:
        stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_member(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        member = await self.get_member(conversation_id, user_id)
        if member is not None:
            return True
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        res = await self.session.execute(stmt)
        conv = res.scalar_one_or_none()
        if conv and not conv.is_group:
            return user_id in (conv.direct_user_low_id, conv.direct_user_high_id)
        return False

    async def add_member(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, role: str = "member"
    ) -> ConversationMember:
        member = ConversationMember(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def touch(self, conversation_id: uuid.UUID) -> None:
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=utc_now())
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def remove_member(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Remove a user from a group conversation. Returns True if removed, False if not found."""
        from sqlalchemy import delete
        stmt = delete(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def update_member_role(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, role: str
    ) -> Optional[ConversationMember]:
        """Update role of a group member (e.g. promote to admin)."""
        stmt = (
            select(ConversationMember)
            .where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
            .options(selectinload(ConversationMember.user))
        )
        result = await self.session.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            member.role = role
            await self.session.flush()
        return member
