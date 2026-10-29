"""User repository for database queries."""

import uuid
from typing import Any, List, Optional, Union
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import normalize_email, normalize_username
from app.db.base import utc_now
from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        normalized = normalize_email(email)
        stmt = select(User).where(User.email == normalized)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        normalized = normalize_username(username)
        stmt = select(User).where(User.username_normalized == normalized)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_username_taken(self, username: str) -> bool:
        normalized = normalize_username(username)
        stmt = select(func.count(User.id)).where(User.username_normalized == normalized)
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def search_users(self, query: str, exclude_user_id: uuid.UUID, limit: int = 20) -> List[User]:
        normalized = normalize_username(query)
        stmt = (
            select(User)
            .where(
                User.id != exclude_user_id,
                User.is_active.is_(True),
                or_(
                    User.username_normalized.ilike(f"%{normalized}%"),
                    User.display_name.ilike(f"%{query}%"),
                ),
            )
            .order_by(User.username_normalized.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_google_sub(self, google_sub: str) -> Optional[User]:
        stmt = select(User).where(User.google_sub == google_sub)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_users_by_normalized_emails(self, emails: List[str]) -> List[User]:
        if not emails:
            return []
        stmt = select(User).where(User.email.in_(emails), User.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_username_or_email(self, identifier: str) -> Optional[User]:
        normalized = identifier.strip().lower()
        stmt = select(User).where(
            or_(User.username_normalized == normalized, User.email == normalized)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        username: str,
        display_name: Optional[str] = None,
        google_sub: Optional[str] = None,
        avatar_url: Optional[str] = None,
        password_hash: Optional[str] = None,
    ) -> User:
        user = User(
            email=normalize_email(email),
            username=username.strip(),
            username_normalized=normalize_username(username),
            display_name=display_name.strip() if display_name else None,
            google_sub=google_sub,
            avatar_url=avatar_url,
            password_hash=password_hash,
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_password_hash(self, user_or_id: Any, password_hash: str) -> Optional[User]:
        if isinstance(user_or_id, uuid.UUID):
            user = await self.get_by_id(user_or_id)
            if not user:
                return None
        else:
            user = user_or_id
        user.password_hash = password_hash
        user.updated_at = utc_now()
        await self.session.flush()
        return user

    async def link_google_identity(
        self,
        user: User,
        google_sub: str,
        avatar_url: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> User:
        user.google_sub = google_sub
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        if display_name and not user.display_name:
            user.display_name = display_name
        user.updated_at = utc_now()
        await self.session.flush()
        return user

