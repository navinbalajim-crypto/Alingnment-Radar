"""Gmail integration and in-app notifications endpoints under /api/v1/gmail."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.oauth import (
    GmailCheckResponse,
    GmailNotificationListResponse,
    GmailStatusResponse,
    GoogleAuthUrlResponse,
    GoogleConnectCallbackRequest,
)
from app.services.gmail_service import GmailNotificationService

router = APIRouter(prefix="/gmail", tags=["Gmail Notifications"])


@router.get("/connect-url", response_model=GoogleAuthUrlResponse, status_code=status.HTTP_200_OK)
async def get_gmail_connect_url(
    redirect_uri: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve Google OAuth consent URL specifically for Gmail inbox metadata notifications."""
    gmail_service = GmailNotificationService(db)
    return gmail_service.get_connect_url(
        user_id=current_user.id,
        redirect_uri=redirect_uri,
    )


@router.post("/callback", response_model=GmailStatusResponse, status_code=status.HTTP_200_OK)
async def connect_gmail_callback(
    payload: GoogleConnectCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exchange authorization code and link Gmail notifications integration to authenticated user."""
    gmail_service = GmailNotificationService(db)
    return await gmail_service.connect_gmail_with_code(
        user_id=current_user.id,
        code=payload.code,
        state=payload.state,
        redirect_uri=payload.redirect_uri,
    )


@router.get("/status", response_model=GmailStatusResponse, status_code=status.HTTP_200_OK)
async def get_gmail_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check status of Gmail notification integration for current user."""
    gmail_service = GmailNotificationService(db)
    return await gmail_service.get_status(user_id=current_user.id)


@router.post("/check", response_model=GmailCheckResponse, status_code=status.HTTP_200_OK)
async def check_gmail_messages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll Gmail for recent email metadata and save in-app notifications (rate-limited)."""
    gmail_service = GmailNotificationService(db)
    return await gmail_service.check_gmail_notifications(user_id=current_user.id)


@router.get("/notifications", response_model=GmailNotificationListResponse, status_code=status.HTTP_200_OK)
async def list_gmail_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List in-app Gmail notifications received for current user."""
    gmail_service = GmailNotificationService(db)
    return await gmail_service.list_notifications(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.post("/notifications/{notification_id}/read", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a specific Gmail notification as read."""
    gmail_service = GmailNotificationService(db)
    success = await gmail_service.mark_as_read(user_id=current_user.id, notification_id=notification_id)
    if not success:
        return MessageResponse(message="Notification not found.")
    return MessageResponse(message="Notification marked as read.")


@router.post("/notifications/read-all", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread Gmail notifications as read for current user."""
    gmail_service = GmailNotificationService(db)
    count = await gmail_service.mark_all_as_read(user_id=current_user.id)
    return MessageResponse(message=f"Marked {count} notification(s) as read.")


@router.delete("", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def disconnect_gmail(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Gmail integration without affecting Google Contacts or active chat session."""
    gmail_service = GmailNotificationService(db)
    await gmail_service.disconnect_gmail(user_id=current_user.id)
    return MessageResponse(message="Gmail integration disconnected.")
