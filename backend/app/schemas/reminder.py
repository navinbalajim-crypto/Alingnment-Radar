"""Pydantic schemas for task reminders and notifications."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TaskReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Title of the task")
    due_at: datetime = Field(..., description="Target due date and time")
    advance_reminder_minutes: int = Field(30, ge=0, le=1440, description="Advance notification minutes")
    responsible_user_id: Optional[uuid.UUID] = Field(None, description="Assigned responsible user")
    timezone: str = Field("Asia/Kolkata", max_length=50, description="Applicable timezone")


class TaskReminderUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    due_at: Optional[datetime] = None
    advance_reminder_minutes: Optional[int] = Field(None, ge=0, le=1440)
    responsible_user_id: Optional[uuid.UUID] = None
    status: Optional[str] = Field(None, pattern="^(pending|completed|cancelled|dismissed)$")
    timezone: Optional[str] = None


class TaskReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    created_by_id: uuid.UUID
    creator_username: Optional[str] = None
    responsible_user_id: Optional[uuid.UUID] = None
    responsible_username: Optional[str] = None
    title: str
    due_at: datetime
    advance_reminder_minutes: int
    advance_scheduled_at: datetime
    timezone: str
    status: str
    advance_delivered: bool
    due_delivered: bool
    created_at: datetime


class UserNotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    reminder_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime


class TaskExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    timezone: str = Field("Asia/Kolkata", max_length=50)


class TaskExtractResponse(BaseModel):
    task_detected: bool
    title: Optional[str] = None
    due_at: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    advance_minutes: int = 30
    confidence: float = 0.0
