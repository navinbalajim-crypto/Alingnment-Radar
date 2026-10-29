"""OAuth connection repository for third-party identity management."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import utc_now
from app.models.oauth_connection import OAuthConnection


class OAuthConnectionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: uuid.UUID, provider: str = "google") -> Optional[OAuthConnection]:
        stmt = select(OAuthConnection).where(
            OAuthConnection.user_id == user_id,
            OAuthConnection.provider == provider,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_provider_user_id(self, provider: str, provider_user_id: str) -> Optional[OAuthConnection]:
        stmt = select(OAuthConnection).where(
            OAuthConnection.provider == provider,
            OAuthConnection.provider_user_id == provider_user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_connection(
        self,
        user_id: uuid.UUID,
        provider: str,
        provider_user_id: str,
        email: Optional[str] = None,
        encrypted_refresh_token: Optional[str] = None,
        access_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        granted_scopes: Optional[str] = None,
        connection_status: str = "active",
    ) -> OAuthConnection:
        existing = await self.get_by_user_id(user_id, provider)
        if existing:
            existing.provider_user_id = provider_user_id
            if email:
                existing.email = email
            if encrypted_refresh_token:
                existing.encrypted_refresh_token = encrypted_refresh_token
            if access_token:
                existing.access_token = access_token
            if token_expires_at:
                existing.token_expires_at = token_expires_at
            if granted_scopes:
                existing.granted_scopes = granted_scopes
            existing.connection_status = connection_status
            existing.updated_at = utc_now()
            await self.session.flush()
            return existing

        conn = OAuthConnection(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            encrypted_refresh_token=encrypted_refresh_token,
            access_token=access_token,
            token_expires_at=token_expires_at,
            granted_scopes=granted_scopes,
            connection_status=connection_status,
        )
        self.session.add(conn)
        await self.session.flush()
        return conn

    async def delete_by_user(self, user_id: uuid.UUID, provider: str = "google") -> bool:
        conn = await self.get_by_user_id(user_id, provider)
        if conn:
            await self.session.delete(conn)
            await self.session.flush()
            return True
        return False
