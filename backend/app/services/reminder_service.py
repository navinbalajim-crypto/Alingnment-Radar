"""Reminder service for persistent task scheduling, updates, and notification delivery."""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.db.base import utc_now
from app.models.reminder import TaskReminder, UserNotification
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.reminder import TaskReminderCreate, TaskReminderRead, TaskReminderUpdate, UserNotificationRead


class ReminderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)

    async def create_reminder(
        self,
        conversation_id: uuid.UUID,
        creator_id: uuid.UUID,
        reminder_in: TaskReminderCreate,
    ) -> TaskReminderRead:
        is_member = await self.conv_repo.is_member(conversation_id, creator_id)
        if not is_member:
            raise ForbiddenError("You are not authorized to schedule reminders in this conversation.")

        due_at = reminder_in.due_at
        if due_at.tzinfo is None:
            from app.services.task_extractor import _get_tz
            tz = _get_tz(reminder_in.timezone)
            due_at = due_at.replace(tzinfo=tz)

        advance_mins = max(0, reminder_in.advance_reminder_minutes)
        advance_scheduled_at = due_at - timedelta(minutes=advance_mins)

        reminder = TaskReminder(
            conversation_id=conversation_id,
            created_by_id=creator_id,
            responsible_user_id=reminder_in.responsible_user_id,
            title=reminder_in.title.strip(),
            due_at=due_at,
            advance_reminder_minutes=advance_mins,
            advance_scheduled_at=advance_scheduled_at,
            timezone=reminder_in.timezone,
            status="pending",
            advance_delivered=False,
            due_delivered=False,
        )
        self.session.add(reminder)
        await self.session.flush()

        # Eagerly load users
        stmt = (
            select(TaskReminder)
            .where(TaskReminder.id == reminder.id)
            .options(
                selectinload(TaskReminder.creator),
                selectinload(TaskReminder.responsible_user),
            )
        )
        fresh = (await self.session.execute(stmt)).scalar_one()
        return self._format_reminder_read(fresh)

    async def get_conversation_reminders(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> List[TaskReminderRead]:
        is_member = await self.conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        stmt = (
            select(TaskReminder)
            .where(TaskReminder.conversation_id == conversation_id)
            .options(
                selectinload(TaskReminder.creator),
                selectinload(TaskReminder.responsible_user),
            )
            .order_by(TaskReminder.due_at.asc())
        )
        result = await self.session.execute(stmt)
        reminders = result.scalars().all()
        return [self._format_reminder_read(r) for r in reminders]

    async def get_user_reminders(self, user_id: uuid.UUID) -> List[TaskReminderRead]:
        stmt = (
            select(TaskReminder)
            .where(
                (TaskReminder.created_by_id == user_id)
                | (TaskReminder.responsible_user_id == user_id)
            )
            .options(
                selectinload(TaskReminder.creator),
                selectinload(TaskReminder.responsible_user),
            )
            .order_by(TaskReminder.due_at.asc())
        )
        result = await self.session.execute(stmt)
        reminders = result.scalars().all()
        return [self._format_reminder_read(r) for r in reminders]

    async def update_reminder(
        self,
        reminder_id: uuid.UUID,
        user_id: uuid.UUID,
        update_in: TaskReminderUpdate,
    ) -> TaskReminderRead:
        stmt = (
            select(TaskReminder)
            .where(TaskReminder.id == reminder_id)
            .options(
                selectinload(TaskReminder.creator),
                selectinload(TaskReminder.responsible_user),
            )
        )
        reminder = (await self.session.execute(stmt)).scalar_one_or_none()
        if not reminder:
            raise NotFoundError("Task reminder not found.")

        # Permission check: Creator or assigned user or conversation member
        is_member = await self.conv_repo.is_member(reminder.conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not authorized to update this reminder.")

        if update_in.title is not None:
            reminder.title = update_in.title.strip()
        if update_in.status is not None:
            reminder.status = update_in.status
        if update_in.responsible_user_id is not None:
            reminder.responsible_user_id = update_in.responsible_user_id
        if update_in.timezone is not None:
            reminder.timezone = update_in.timezone

        recalculate_advance = False
        if update_in.due_at is not None:
            reminder.due_at = update_in.due_at
            recalculate_advance = True
        if update_in.advance_reminder_minutes is not None:
            reminder.advance_reminder_minutes = max(0, update_in.advance_reminder_minutes)
            recalculate_advance = True

        if recalculate_advance:
            reminder.advance_scheduled_at = reminder.due_at - timedelta(minutes=reminder.advance_reminder_minutes)
            # Reset delivery if schedule moved forward
            now = utc_now()
            if reminder.due_at > now:
                reminder.due_delivered = False
            if reminder.advance_scheduled_at > now:
                reminder.advance_delivered = False

        await self.session.flush()
        return self._format_reminder_read(reminder)

    async def delete_reminder(self, reminder_id: uuid.UUID, user_id: uuid.UUID) -> None:
        stmt = select(TaskReminder).where(TaskReminder.id == reminder_id)
        reminder = (await self.session.execute(stmt)).scalar_one_or_none()
        if not reminder:
            raise NotFoundError("Task reminder not found.")

        is_member = await self.conv_repo.is_member(reminder.conversation_id, user_id)
        if not is_member:
            raise ForbiddenError("You are not authorized to delete this reminder.")

        if reminder.created_by_id != user_id and reminder.responsible_user_id != user_id:
            raise ForbiddenError("Only the creator or responsible user may cancel this reminder.")

        await self.session.delete(reminder)
        await self.session.flush()

    async def get_user_notifications(
        self, user_id: uuid.UUID, unread_only: bool = False
    ) -> List[UserNotificationRead]:
        stmt = select(UserNotification).where(UserNotification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(UserNotification.is_read.is_(False))
        stmt = stmt.order_by(UserNotification.created_at.desc()).limit(100)
        result = await self.session.execute(stmt)
        return [UserNotificationRead.model_validate(n) for n in result.scalars().all()]

    async def mark_notification_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> UserNotificationRead:
        stmt = select(UserNotification).where(
            UserNotification.id == notification_id,
            UserNotification.user_id == user_id,
        )
        notif = (await self.session.execute(stmt)).scalar_one_or_none()
        if not notif:
            raise NotFoundError("Notification not found.")

        notif.is_read = True
        await self.session.flush()
        return UserNotificationRead.model_validate(notif)

    def _format_reminder_read(self, r: TaskReminder) -> TaskReminderRead:
        return TaskReminderRead(
            id=r.id,
            conversation_id=r.conversation_id,
            created_by_id=r.created_by_id,
            creator_username=r.creator.username if r.creator else None,
            responsible_user_id=r.responsible_user_id,
            responsible_username=r.responsible_user.username if r.responsible_user else None,
            title=r.title,
            due_at=r.due_at,
            advance_reminder_minutes=r.advance_reminder_minutes,
            advance_scheduled_at=r.advance_scheduled_at,
            timezone=r.timezone,
            status=r.status,
            advance_delivered=r.advance_delivered,
            due_delivered=r.due_delivered,
            created_at=r.created_at,
        )
