"""Group invitation repository for invitation management."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.invitation import GroupInvitation


class InvitationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_invitation(
        self,
        group_id: uuid.UUID,
        created_by_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        max_uses: Optional[int] = None,
    ) -> GroupInvitation:
        invitation = GroupInvitation(
            group_id=group_id,
            created_by_id=created_by_id,
            token_hash=token_hash,
            expires_at=expires_at,
            max_uses=max_uses,
            uses_count=0,
            is_revoked=False,
        )
        self.session.add(invitation)
        await self.session.flush()
        return await self.get_by_id(invitation.id)  # type: ignore

    async def get_by_id(self, invitation_id: uuid.UUID) -> Optional[GroupInvitation]:
        stmt = (
            select(GroupInvitation)
            .where(GroupInvitation.id == invitation_id)
            .options(
                selectinload(GroupInvitation.group),
                selectinload(GroupInvitation.created_by),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> Optional[GroupInvitation]:
        stmt = (
            select(GroupInvitation)
            .where(GroupInvitation.token_hash == token_hash)
            .options(
                selectinload(GroupInvitation.group),
                selectinload(GroupInvitation.created_by),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def increment_uses(self, invitation: GroupInvitation) -> int:
        invitation.uses_count += 1
        await self.session.flush()
        return invitation.uses_count

    async def revoke_invitation(self, invitation: GroupInvitation) -> None:
        invitation.is_revoked = True
        await self.session.flush()
