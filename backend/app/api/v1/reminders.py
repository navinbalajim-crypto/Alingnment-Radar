"""Task reminder and notification endpoints."""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.reminder import (
    TaskExtractRequest,
    TaskExtractResponse,
    TaskReminderCreate,
    TaskReminderRead,
    TaskReminderUpdate,
    UserNotificationRead,
)
from app.services.reminder_service import ReminderService
from app.services.task_extractor import extract_task_from_text

router = APIRouter(tags=["Reminders"])


@router.post(
    "/conversations/{conversation_id}/reminders/extract",
    response_model=TaskExtractResponse,
    status_code=status.HTTP_200_OK,
)
async def extract_task(
    conversation_id: uuid.UUID,
    payload: TaskExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect task and schedule details from natural language text without saving."""
    from app.repositories.conversation_repo import ConversationRepository
    from app.core.errors import ForbiddenError

    conv_repo = ConversationRepository(db)
    is_member = await conv_repo.is_member(conversation_id, current_user.id)
    if not is_member:
        raise ForbiddenError("You are not a member of this conversation.")

    result = extract_task_from_text(payload.text, tz_name=payload.timezone)
    if not result:
        return TaskExtractResponse(task_detected=False, timezone=payload.timezone)

    return TaskExtractResponse(
        task_detected=True,
        title=result["title"],
        due_at=result["due_at"],
        timezone=result.get("timezone", payload.timezone),
        advance_minutes=result.get("advance_minutes", 30),
        confidence=result.get("confidence", 0.9),
    )


@router.post(
    "/conversations/{conversation_id}/reminders",
    response_model=TaskReminderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_reminder(
    conversation_id: uuid.UUID,
    payload: TaskReminderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a persistent task reminder in the conversation with advance and due schedules."""
    service = ReminderService(db)
    reminder = await service.create_reminder(
        conversation_id=conversation_id,
        creator_id=current_user.id,
        reminder_in=payload,
    )
    await db.commit()
    return reminder


@router.get(
    "/conversations/{conversation_id}/reminders",
    response_model=List[TaskReminderRead],
    status_code=status.HTTP_200_OK,
)
async def get_conversation_reminders(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List scheduled reminders for a specific conversation."""
    service = ReminderService(db)
    return await service.get_conversation_reminders(conversation_id, current_user.id)


@router.get(
    "/reminders",
    response_model=List[TaskReminderRead],
    status_code=status.HTTP_200_OK,
)
async def get_user_reminders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all scheduled reminders created by or assigned to the current user."""
    service = ReminderService(db)
    return await service.get_user_reminders(current_user.id)


@router.patch(
    "/reminders/{reminder_id}",
    response_model=TaskReminderRead,
    status_code=status.HTTP_200_OK,
)
async def update_reminder(
    reminder_id: uuid.UUID,
    payload: TaskReminderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update title, schedule, assignment, or completion status of a reminder."""
    service = ReminderService(db)
    updated = await service.update_reminder(reminder_id, current_user.id, payload)
    await db.commit()
    return updated


@router.delete(
    "/reminders/{reminder_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_reminder(
    reminder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel or remove a scheduled reminder."""
    service = ReminderService(db)
    await service.delete_reminder(reminder_id, current_user.id)
    await db.commit()
    return {"status": "ok", "message": "Reminder cancelled successfully."}


@router.get(
    "/notifications",
    response_model=List[UserNotificationRead],
    status_code=status.HTTP_200_OK,
)
async def get_user_notifications(
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve in-app notifications for current user (including offline backlog)."""
    service = ReminderService(db)
    return await service.get_user_notifications(current_user.id, unread_only=unread_only)


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=UserNotificationRead,
    status_code=status.HTTP_200_OK,
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    service = ReminderService(db)
    updated = await service.mark_notification_read(notification_id, current_user.id)
    await db.commit()
    return updated
