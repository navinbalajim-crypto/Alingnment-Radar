"""Google OAuth request and response schemas."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GoogleAuthUrlResponse(BaseModel):
    url: str = Field(..., description="Full Google OAuth2 consent authorization URL")
    state: str = Field(..., description="Cryptographic state verification nonce")


class GoogleAuthCallbackRequest(BaseModel):
    code: str = Field(..., description="Authorization code returned by Google")
    state: Optional[str] = Field(None, description="State token returned by Google")
    redirect_uri: Optional[str] = Field(None, description="Redirect URI passed in initial authorization")


class OAuthStatusResponse(BaseModel):
    connected: bool
    provider: str = "google"
    email: Optional[str] = None
    has_contacts_scope: bool = False
    connected_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None


class GoogleConnectCallbackRequest(BaseModel):
    code: str = Field(..., description="Authorization code returned by Google")
    state: str = Field(..., description="Signed OAuth state returned by Google")
    redirect_uri: Optional[str] = Field(None, description="Redirect URI used in initial request")


class GoogleContactsStatusResponse(BaseModel):
    connected: bool
    provider: str = "google_contacts"
    email: Optional[str] = None
    granted_scopes: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    matched_registered_count: int = 0


class GmailStatusResponse(BaseModel):
    connected: bool
    provider: str = "google_gmail"
    email: Optional[str] = None
    granted_scopes: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    unread_notifications_count: int = 0
    polling_interval_seconds: int = 60
    delivery_mechanism: str = "polling"


class GmailNotificationItem(BaseModel):
    id: uuid.UUID
    gmail_message_id: str
    gmail_thread_id: Optional[str] = None
    sender: Optional[str] = None
    subject: Optional[str] = None
    snippet: Optional[str] = None
    received_at: Optional[datetime] = None
    is_read: bool = False
    created_at: datetime


class GmailNotificationListResponse(BaseModel):
    notifications: list[GmailNotificationItem]
    unread_count: int
    total_count: int


class GmailCheckResponse(BaseModel):
    new_notifications_count: int
    unread_count: int
    message: str

