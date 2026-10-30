"""Group conversation management endpoints under /api/v1/groups."""

import uuid
from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.errors import BadRequestError
from app.db.session import get_db
from app.models.user import User
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.auth import MessageResponse
from app.schemas.conversation import ConversationSummary
from app.schemas.group import (
    CreateGroupRequest,
    CreateInvitationRequest,
    GroupDetailResponse,
    GroupMemberResponse,
    InvitationResponse,
)
from app.services.avatar_service import AvatarService
from app.services.group_service import GroupService
from app.services.invitation_service import InvitationService

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.post("", response_model=GroupDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: CreateGroupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new group conversation. Creator becomes initial admin."""
    group_service = GroupService(db)
    return await group_service.create_group(creator_id=current_user.id, group_in=payload)


@router.get("", response_model=List[ConversationSummary], status_code=status.HTTP_200_OK)
async def list_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all group conversations that current user is a member of."""
    group_service = GroupService(db)
    return await group_service.list_user_groups(current_user.id)


@router.get("/{group_id}", response_model=GroupDetailResponse, status_code=status.HTTP_200_OK)
async def get_group(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get group details including membership list."""
    group_service = GroupService(db)
    return await group_service.get_group(group_id=group_id, current_user_id=current_user.id)


@router.get("/{group_id}/members", response_model=List[GroupMemberResponse], status_code=status.HTTP_200_OK)
async def get_group_members(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List members of a group with their roles and join dates."""
    group_service = GroupService(db)
    return await group_service.get_group_members(group_id=group_id, current_user_id=current_user.id)


@router.post("/{group_id}/avatar", response_model=GroupDetailResponse, status_code=status.HTTP_200_OK)
async def upload_group_avatar(
    group_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload or replace a group's display picture (max 3 MB, JPEG/PNG/WebP/GIF). Group admins only."""
    group_service = GroupService(db)
    try:
        result = await group_service.set_group_avatar(group_id, current_user.id, file)
    except BadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return result


@router.delete("/{group_id}/avatar", response_model=GroupDetailResponse, status_code=status.HTTP_200_OK)
async def delete_group_avatar(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a group's custom display picture, restoring the default avatar. Group admins only."""
    group_service = GroupService(db)
    result = await group_service.remove_group_avatar(group_id, current_user.id)
    await db.commit()
    return result


@router.get("/{group_id}/avatar", status_code=status.HTTP_200_OK)
async def get_group_avatar(
    group_id: uuid.UUID,
):
    """Serve a group's display picture."""
    found = AvatarService.get_group_avatar_file(group_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No photo set for this group.")
    file_path, content_type = found
    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/{group_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_group_invitation(
    group_id: uuid.UUID,
    payload: CreateInvitationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a secure group invitation URL. Requires group admin privileges."""
    invitation_service = InvitationService(db)
    return await invitation_service.create_invitation(
        group_id=group_id,
        current_user_id=current_user.id,
        max_uses=payload.max_uses,
        expires_in_days=payload.expires_in_days,
    )


@router.delete("/{group_id}/invitations/{invitation_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def revoke_group_invitation(
    group_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an invitation token. Requires group admin privileges."""
    invitation_service = InvitationService(db)
    await invitation_service.revoke_invitation(
        group_id=group_id,
        invitation_id=invitation_id,
        current_user_id=current_user.id,
    )
    return MessageResponse(message="Invitation successfully revoked.")


@router.post("/{group_id}/members/{user_id}/promote", response_model=GroupMemberResponse, status_code=status.HTTP_200_OK)
async def promote_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote a group member to admin. Requires group admin privileges."""
    group_service = GroupService(db)
    promoted = await group_service.promote_member(
        group_id=group_id,
        target_user_id=user_id,
        current_user_id=current_user.id,
    )
    await db.commit()
    return promoted


@router.delete("/{group_id}/members/{user_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def remove_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a group. Requires group admin privileges."""
    group_service = GroupService(db)
    await group_service.remove_member(
        group_id=group_id,
        target_user_id=user_id,
        current_user_id=current_user.id,
    )
    await db.commit()
    return MessageResponse(message="Member removed from group.")


@router.post("/{group_id}/leave", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def leave_group(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Leave a group conversation voluntarily."""
    group_service = GroupService(db)
    await group_service.leave_group(
        group_id=group_id,
        current_user_id=current_user.id,
    )
    await db.commit()
    return MessageResponse(message="You have left the group.")

