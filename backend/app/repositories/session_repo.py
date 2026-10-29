"""Refresh session repository for token rotation and invalidation."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import utc_now
from app.models.session import RefreshSession


class SessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> RefreshSession:
        db_session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            is_revoked=False,
            last_used_at=utc_now(),
        )
        self.session.add(db_session)
        await self.session.flush()
        return db_session

    async def get_active_session_by_hash(self, token_hash: str) -> Optional[RefreshSession]:
        stmt = select(RefreshSession).where(
            RefreshSession.token_hash == token_hash,
            RefreshSession.is_revoked.is_(False),
        )
        result = await self.session.execute(stmt)
        session = result.scalar_one_or_none()
        if session and session.is_active():
            return session
        return None

    async def revoke_session(self, db_session: RefreshSession) -> None:
        db_session.is_revoked = True
        await self.session.flush()

    async def revoke_all_user_sessions(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id)
            .values(is_revoked=True)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def rotate_session(
        self,
        old_session: RefreshSession,
        new_token_hash: str,
        new_expires_at: datetime,
    ) -> RefreshSession:
        old_session.is_revoked = True
        new_session = RefreshSession(
            user_id=old_session.user_id,
            token_hash=new_token_hash,
            expires_at=new_expires_at,
            user_agent=old_session.user_agent,
            ip_address=old_session.ip_address,
            is_revoked=False,
            last_used_at=utc_now(),
        )
        self.session.add(new_session)
        await self.session.flush()
        return new_session
