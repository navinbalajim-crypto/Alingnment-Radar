"""Background persistent scheduler and dispatcher for task reminders."""

import asyncio
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.db.base import utc_now
from app.db.session import AsyncSessionLocal
from app.models.reminder import TaskReminder, UserNotification
from app.sockets.connection_manager import connection_manager
from app.sockets.server import sio

_worker_task: Optional[asyncio.Task] = None
_should_stop: bool = False


async def check_and_dispatch_reminders(db: Optional[AsyncSession] = None) -> int:
    """
    Check pending reminders and deliver advance/due notifications.
    Durable, idempotent: commits delivery flags with notifications.
    Returns count of delivered events.
    """
    now = utc_now()
    delivered_count = 0

    async def _execute_dispatch(session: AsyncSession) -> int:
        nonlocal delivered_count
        # 1. Advance reminders due for delivery
        stmt_advance = (
            select(TaskReminder)
            .where(
                TaskReminder.status == "pending",
                TaskReminder.advance_delivered.is_(False),
                TaskReminder.advance_scheduled_at <= now,
            )
            .limit(50)
        )
        advance_results = (await session.execute(stmt_advance)).scalars().all()

        for rem in advance_results:
            rem.advance_delivered = True
            recipients = {rem.created_by_id}
            if rem.responsible_user_id:
                recipients.add(rem.responsible_user_id)

            for uid in recipients:
                notif = UserNotification(
                    id=uuid.uuid4(),
                    user_id=uid,
                    reminder_id=rem.id,
                    conversation_id=rem.conversation_id,
                    type="advance_reminder",
                    title=f"Upcoming: {rem.title}",
                    message=f"Reminder: '{rem.title}' is scheduled for {rem.due_at.strftime('%I:%M %p')}.",
                    is_read=False,
                )
                session.add(notif)

                # Emit to connected sockets for this user
                sids = connection_manager.get_user_sids(uid)
                for sid in sids:
                    await sio.emit(
                        "reminder:notify",
                        {
                            "id": str(notif.id),
                            "reminder_id": str(rem.id),
                            "conversation_id": str(rem.conversation_id),
                            "title": notif.title,
                            "message": notif.message,
                            "type": "advance",
                            "due_at": rem.due_at.isoformat(),
                        },
                        room=sid,
                    )
            delivered_count += 1

        # 2. Due-time reminders due for delivery
        stmt_due = (
            select(TaskReminder)
            .where(
                TaskReminder.status == "pending",
                TaskReminder.due_delivered.is_(False),
                TaskReminder.due_at <= now,
            )
            .limit(50)
        )
        due_results = (await session.execute(stmt_due)).scalars().all()

        for rem in due_results:
            rem.due_delivered = True
            recipients = {rem.created_by_id}
            if rem.responsible_user_id:
                recipients.add(rem.responsible_user_id)

            for uid in recipients:
                notif = UserNotification(
                    id=uuid.uuid4(),
                    user_id=uid,
                    reminder_id=rem.id,
                    conversation_id=rem.conversation_id,
                    type="due_reminder",
                    title=f"Due now: {rem.title}",
                    message=f"Task due now: '{rem.title}'.",
                    is_read=False,
                )
                session.add(notif)

                sids = connection_manager.get_user_sids(uid)
                for sid in sids:
                    await sio.emit(
                        "reminder:notify",
                        {
                            "id": str(notif.id),
                            "reminder_id": str(rem.id),
                            "conversation_id": str(rem.conversation_id),
                            "title": notif.title,
                            "message": notif.message,
                            "type": "due",
                            "due_at": rem.due_at.isoformat(),
                        },
                        room=sid,
                    )
            delivered_count += 1

        if delivered_count > 0:
            await session.commit()
        return delivered_count

    if db is not None:
        return await _execute_dispatch(db)

    async with AsyncSessionLocal() as session:
        return await _execute_dispatch(session)


async def reminder_worker_loop(interval_seconds: float = 10.0):
    """Periodic loop checking and dispatching scheduled reminders."""
    global _should_stop
    logger.info("Reminder background worker started.")
    while not _should_stop:
        try:
            await check_and_dispatch_reminders()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Error in reminder worker loop: {exc}")
        await asyncio.sleep(interval_seconds)
    logger.info("Reminder background worker stopped.")


def start_reminder_worker(interval_seconds: float = 10.0) -> asyncio.Task:
    global _worker_task, _should_stop
    _should_stop = False
    _worker_task = asyncio.create_task(reminder_worker_loop(interval_seconds))
    return _worker_task


def stop_reminder_worker():
    global _worker_task, _should_stop
    _should_stop = True
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
