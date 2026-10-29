"""Gmail notification repository for storing and managing Gmail inbox alerts."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import utc_now
from app.models.gmail_notification import GmailNotification


class GmailNotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Optional[GmailNotification]:
        stmt = select(GmailNotification).where(
            GmailNotification.id == notification_id,
            GmailNotification.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[GmailNotification]:
        stmt = select(GmailNotification).where(GmailNotification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(GmailNotification.is_read.is_(False))
        stmt = stmt.order_by(GmailNotification.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(self, user_id: uuid.UUID, unread_only: bool = False) -> int:
        stmt = select(func.count(GmailNotification.id)).where(GmailNotification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(GmailNotification.is_read.is_(False))
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_existing_message_ids(self, user_id: uuid.UUID, message_ids: List[str]) -> Set[str]:
        if not message_ids:
            return set()
        stmt = select(GmailNotification.gmail_message_id).where(
            GmailNotification.user_id == user_id,
            GmailNotification.gmail_message_id.in_(message_ids),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def create_notification(
        self,
        user_id: uuid.UUID,
        gmail_message_id: str,
        gmail_thread_id: Optional[str] = None,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
        snippet: Optional[str] = None,
        received_at: Optional[datetime] = None,
    ) -> GmailNotification:
        notification = GmailNotification(
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            gmail_thread_id=gmail_thread_id,
            sender=sender,
            subject=subject,
            snippet=snippet,
            received_at=received_at or utc_now(),
            is_read=False,
            created_at=utc_now(),
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def bulk_create_notifications(
        self,
        user_id: uuid.UUID,
        items: List[Dict[str, Any]],
    ) -> int:
        created_count = 0
        now = utc_now()
        for item in items:
            notif = GmailNotification(
                user_id=user_id,
                gmail_message_id=item["gmail_message_id"],
                gmail_thread_id=item.get("gmail_thread_id"),
                sender=item.get("sender"),
                subject=item.get("subject"),
                snippet=item.get("snippet"),
                received_at=item.get("received_at") or now,
                is_read=False,
                created_at=now,
            )
            self.session.add(notif)
            created_count += 1
        if created_count > 0:
            await self.session.flush()
        return created_count

    async def mark_as_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        stmt = (
            update(GmailNotification)
            .where(
                GmailNotification.id == notification_id,
                GmailNotification.user_id == user_id,
            )
            .values(is_read=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        stmt = (
            update(GmailNotification)
            .where(
                GmailNotification.user_id == user_id,
                GmailNotification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        stmt = delete(GmailNotification).where(GmailNotification.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0
