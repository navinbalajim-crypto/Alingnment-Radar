"""User profile and discovery endpoints under /api/v1/users."""

import uuid
from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.errors import BadRequestError
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import AiPreferences, AiPreferencesUpdate, UserPrivate, UserPublic, UsernameAvailabilityResponse
from app.services.avatar_service import AvatarService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserPrivate, status_code=status.HTTP_200_OK)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve private authenticated profile of current user."""
    user_service = UserService(db)
    return await user_service.get_me(current_user.id)


@router.get("/search", response_model=List[UserPublic], status_code=status.HTTP_200_OK)
async def search_users(
    username: str = Query(..., min_length=1, description="Username or display name search query"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search registered users by username, excluding the requesting user."""
    user_service = UserService(db)
    return await user_service.search_users(query=username, current_user_id=current_user.id, limit=limit)


@router.get("/username-availability", response_model=UsernameAvailabilityResponse, status_code=status.HTTP_200_OK)
async def check_username_availability(
    username: str = Query(..., min_length=1, description="Username to check for availability"),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to check if a username is valid and available."""
    user_service = UserService(db)
    return await user_service.check_username_availability(username)


@router.post("/me/avatar", response_model=UserPrivate, status_code=status.HTTP_200_OK)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload or replace the authenticated user's profile picture (max 3 MB, JPEG/PNG/WebP/GIF)."""
    user = await db.get(User, current_user.id)
    service = AvatarService(db)
    try:
        await service.set_avatar(user, file)
    except BadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}/avatar", status_code=status.HTTP_200_OK)
async def get_avatar(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Serve a user's profile picture. Requires authentication; any signed-in user may view
    any other user's avatar, consistent with avatars being visible wherever a user appears
    (search results, contacts, group member lists)."""
    found = AvatarService.get_avatar_file(user_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar set for this user.")
    file_path, content_type = found
    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        # Safe to cache long-term: the URL is versioned with a `?v=` query param that
        # changes on every re-upload, so a cached response can never go stale.
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=31536000, immutable"},
    )


def _prefs_of(user: User) -> AiPreferences:
    return AiPreferences(
        ai_draft_analysis=bool(user.ai_draft_analysis_consent),
        ai_autocomplete=bool(user.ai_autocomplete_consent),
        draft_recommendations=bool(user.draft_recommendations_consent),
    )


@router.get("/me/ai-preferences", response_model=AiPreferences, status_code=status.HTTP_200_OK)
async def get_ai_preferences(current_user: User = Depends(get_current_user)):
    """Current consent for external processing of unsent drafts (default: all disabled)."""
    return _prefs_of(current_user)


@router.put("/me/ai-preferences", response_model=AiPreferences, status_code=status.HTTP_200_OK)
async def update_ai_preferences(
    payload: AiPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant or revoke consent. Only the supplied flags change; no draft content is involved or stored."""
    user = await db.get(User, current_user.id)
    for field, column in (
        ("ai_draft_analysis", "ai_draft_analysis_consent"),
        ("ai_autocomplete", "ai_autocomplete_consent"),
        ("draft_recommendations", "draft_recommendations_consent"),
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, column, value)
    await db.flush()
    return _prefs_of(user)
