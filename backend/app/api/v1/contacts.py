"""Contacts and Google People API integration endpoints under /api/v1/contacts."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.contact import ContactListResponse, SyncContactsResponse
from app.schemas.oauth import (
    GoogleAuthUrlResponse,
    GoogleConnectCallbackRequest,
    GoogleContactsStatusResponse,
    OAuthStatusResponse,
)
from app.services.contact_service import ContactService
from app.services.google_auth_service import GoogleAuthService

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.get("", response_model=ContactListResponse, status_code=status.HTTP_200_OK)
async def list_contacts(
    query: Optional[str] = Query(None, description="Optional search filter by name or email"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List authenticated user's address book contacts, displaying only registered app teammates."""
    contact_service = ContactService(db)
    return await contact_service.list_user_contacts(
        user_id=current_user.id,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get("/google/connect-url", response_model=GoogleAuthUrlResponse, status_code=status.HTTP_200_OK)
async def get_google_contacts_connect_url(
    redirect_uri: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate Google OAuth URL specifically for Google Contacts incremental authorization."""
    google_service = GoogleAuthService(db)
    return google_service.get_contacts_connect_url(
        user_id=current_user.id,
        redirect_uri=redirect_uri,
    )


@router.post("/google/callback", response_model=GoogleContactsStatusResponse, status_code=status.HTTP_200_OK)
async def connect_google_contacts_callback(
    payload: GoogleConnectCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exchange authorization code and link Google Contacts integration to authenticated user."""
    google_service = GoogleAuthService(db)
    return await google_service.connect_contacts_with_code(
        user_id=current_user.id,
        code=payload.code,
        state=payload.state,
        redirect_uri=payload.redirect_uri,
    )


@router.get("/google/status", response_model=GoogleContactsStatusResponse, status_code=status.HTTP_200_OK)
async def get_google_contacts_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if current user has an active Google Contacts connection."""
    google_service = GoogleAuthService(db)
    return await google_service.get_contacts_status(user_id=current_user.id)


@router.get("/google-status", response_model=OAuthStatusResponse, status_code=status.HTTP_200_OK)
async def get_google_connection_status_legacy(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy endpoint: Check if current user has an active Google OAuth connection."""
    google_service = GoogleAuthService(db)
    return await google_service.get_oauth_status(user_id=current_user.id)


@router.post("/sync-google", response_model=SyncContactsResponse, status_code=status.HTTP_200_OK)
async def sync_google_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger on-demand synchronization with Google People API."""
    contact_service = ContactService(db)
    return await contact_service.sync_google_contacts(user_id=current_user.id)


@router.delete("/google", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def disconnect_google_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Google Contacts integration and delete synced address book contacts."""
    google_service = GoogleAuthService(db)
    await google_service.disconnect_contacts(user_id=current_user.id)
    return MessageResponse(message="Google Contacts disconnected and imported contacts removed.")
