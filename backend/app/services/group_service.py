"""Group management service for group creation and membership controls."""

import uuid
from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.core.logging import logger
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.conversation import ConversationSummary
from app.schemas.group import CreateGroupRequest, GroupDetailResponse, GroupMemberResponse
from app.services.avatar_service import AvatarService
from app.services.conversation_service import ConversationService


class GroupService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.user_repo = UserRepository(session)
        self.conv_service = ConversationService(session)

    async def create_group(
        self, creator_id: uuid.UUID, group_in: CreateGroupRequest
    ) -> GroupDetailResponse:
        initial_member_ids: List[uuid.UUID] = []
        if group_in.initial_member_usernames:
            for username in group_in.initial_member_usernames:
                user = await self.user_repo.get_by_username(username)
                if user and user.id != creator_id:
                    initial_member_ids.append(user.id)

        conv = await self.conv_repo.create_group_conversation(
            title=group_in.title,
            creator_id=creator_id,
            initial_member_ids=initial_member_ids,
        )

        return self._format_group_detail(conv)

    async def get_group(self, group_id: uuid.UUID, current_user_id: uuid.UUID) -> GroupDetailResponse:
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        is_member = await self.conv_repo.is_member(group_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this group.")

        return self._format_group_detail(conv)

    async def list_user_groups(self, current_user_id: uuid.UUID) -> List[ConversationSummary]:
        all_convs = await self.conv_repo.get_user_conversations(current_user_id)
        groups = [c for c in all_convs if c.is_group]
        summaries: List[ConversationSummary] = []
        for g in groups:
            summary = await self.conv_service._format_conversation_summary(g, current_user_id)
            summaries.append(summary)
        return summaries

    async def get_group_members(
        self, group_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> List[GroupMemberResponse]:
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        is_member = await self.conv_repo.is_member(group_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this group.")

        members = []
        for m in conv.members:
            if m.user:
                members.append(
                    GroupMemberResponse(
                        id=m.id,
                        user_id=m.user_id,
                        username=m.user.username,
                        display_name=m.user.display_name,
                        role=m.role,
                        joined_at=m.joined_at,
                    )
                )
        return members

    def _format_group_detail(self, conv) -> GroupDetailResponse:
        members = []
        for m in conv.members:
            if m.user:
                members.append(
                    GroupMemberResponse(
                        id=m.id,
                        user_id=m.user_id,
                        username=m.user.username,
                        display_name=m.user.display_name,
                        role=m.role,
                        joined_at=m.joined_at,
                    )
                )

        return GroupDetailResponse(
            id=conv.id,
            title=conv.title or "Untitled Group",
            avatar_url=conv.avatar_url,
            created_by_id=conv.created_by_id,
            members=members,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    async def promote_member(
        self,
        group_id: uuid.UUID,
        target_user_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> GroupMemberResponse:
        """Admin promotes another group member to admin."""
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        requester = await self.conv_repo.get_member(group_id, current_user_id)
        if not requester or requester.role != "admin":
            raise ForbiddenError("Only group admins can promote members.")

        target = await self.conv_repo.get_member(group_id, target_user_id)
        if not target:
            raise NotFoundError("Member not found in this group.")

        updated_member = await self.conv_repo.update_member_role(group_id, target_user_id, "admin")
        if not updated_member or not updated_member.user:
            raise NotFoundError("Failed to update member role.")

        # Real-time event to group
        try:
            from app.sockets.server import sio
            await sio.emit(
                "group:role_updated",
                {
                    "group_id": str(group_id),
                    "user_id": str(target_user_id),
                    "role": "admin",
                },
                room=f"conversation:{group_id}",
            )
        except Exception as exc:
            logger.warning(f"Failed to emit group:role_updated: {exc}")

        return GroupMemberResponse(
            id=updated_member.id,
            user_id=updated_member.user_id,
            username=updated_member.user.username,
            display_name=updated_member.user.display_name,
            role="admin",
            joined_at=updated_member.joined_at,
        )

    async def remove_member(
        self,
        group_id: uuid.UUID,
        target_user_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> None:
        """Admin removes another member from the group with last-admin protection."""
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        # Check requester is admin
        requester = await self.conv_repo.get_member(group_id, current_user_id)
        if not requester or requester.role != "admin":
            raise ForbiddenError("Only group admins can remove members.")

        if target_user_id == current_user_id:
            raise BadRequestError("Admins cannot remove themselves. Use leave_group instead.")

        target = await self.conv_repo.get_member(group_id, target_user_id)
        if not target:
            raise NotFoundError("Member not found in this group.")

        # Last-admin protection
        if target.role == "admin":
            members = await self.conv_repo.get_members(group_id)
            admin_count = sum(1 for m in members if m.role == "admin")
            if admin_count <= 1:
                raise BadRequestError("Cannot remove the last group admin.")

        removed = await self.conv_repo.remove_member(group_id, target_user_id)
        if not removed:
            raise NotFoundError("Member not found in this group.")

        # Evict target user's active sockets from the room
        try:
            from app.sockets.connection_manager import connection_manager
            from app.sockets.server import sio

            room_name = f"conversation:{group_id}"
            user_sids = connection_manager.get_user_connections(target_user_id)
            for sid in user_sids:
                await sio.leave_room(sid, room_name)
                # Notify removed user directly
                await sio.emit(
                    "group:member_removed",
                    {"group_id": str(group_id), "user_id": str(target_user_id)},
                    room=sid,
                )

            # Broadcast to remaining room members
            await sio.emit(
                "group:member_left",
                {"group_id": str(group_id), "user_id": str(target_user_id)},
                room=room_name,
            )
            await sio.emit(
                "group:member_removed",
                {"group_id": str(group_id), "user_id": str(target_user_id)},
                room=room_name,
            )
            logger.info(f"Evicted and notified user={target_user_id} removed from group={group_id}")
        except Exception as exc:
            logger.warning(f"Failed to evict socket or emit group:member_left: {exc}")

    async def set_group_avatar(
        self,
        group_id: uuid.UUID,
        current_user_id: uuid.UUID,
        upload_file: UploadFile,
    ) -> GroupDetailResponse:
        """Upload or replace a group's display picture. Restricted to group admins, the same
        authorization level this service already uses for every other group-wide change
        (invitations, promoting/removing members) -- there is no existing precedent in this
        app for ordinary members editing shared group details, so admin-only is the smallest
        consistent policy rather than a new permission tier."""
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        requester = await self.conv_repo.get_member(group_id, current_user_id)
        if not requester or requester.role != "admin":
            raise ForbiddenError("Only group admins can change the group photo.")

        avatar_service = AvatarService(self.session)
        try:
            await avatar_service.set_group_avatar(conv, upload_file)
        except BadRequestError:
            raise
        await self.session.flush()

        await self._broadcast_group_avatar_update(group_id, conv.avatar_url)
        return self._format_group_detail(conv)

    async def remove_group_avatar(
        self,
        group_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> GroupDetailResponse:
        """Remove a group's custom display picture, restoring the default avatar. Admin-only,
        matching `set_group_avatar`."""
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        requester = await self.conv_repo.get_member(group_id, current_user_id)
        if not requester or requester.role != "admin":
            raise ForbiddenError("Only group admins can remove the group photo.")

        AvatarService.remove_group_avatar(conv)
        await self.session.flush()

        await self._broadcast_group_avatar_update(group_id, None)
        return self._format_group_detail(conv)

    @staticmethod
    async def _broadcast_group_avatar_update(group_id: uuid.UUID, avatar_url: Optional[str]) -> None:
        """Notify every connected, authorized group member so the header and sidebar update
        live, the same way group:role_updated already does for role changes. Scoped to the
        group's own Socket.IO room, which only members are ever joined to."""
        try:
            from app.sockets.server import sio
            await sio.emit(
                "group:avatar_updated",
                {"group_id": str(group_id), "avatar_url": avatar_url},
                room=f"conversation:{group_id}",
            )
        except Exception as exc:
            logger.warning(f"Failed to emit group:avatar_updated: {exc}")

    async def leave_group(
        self,
        group_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> None:
        """Current user leaves the group voluntarily with last-admin protection."""
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        member = await self.conv_repo.get_member(group_id, current_user_id)
        if not member:
            raise ForbiddenError("You are not a member of this group.")

        members = await self.conv_repo.get_members(group_id)
        if member.role == "admin" and len(members) > 1:
            admin_count = sum(1 for m in members if m.role == "admin")
            if admin_count <= 1:
                raise BadRequestError("Cannot leave as the last group admin. Please promote another member to admin first.")

        removed = await self.conv_repo.remove_member(group_id, current_user_id)
        if not removed:
            raise NotFoundError("Member record not found.")

        # Evict leaving user's sockets from room
        try:
            from app.sockets.connection_manager import connection_manager
            from app.sockets.server import sio

            room_name = f"conversation:{group_id}"
            user_sids = connection_manager.get_user_connections(current_user_id)
            for sid in user_sids:
                await sio.leave_room(sid, room_name)

            await sio.emit(
                "group:member_left",
                {"group_id": str(group_id), "user_id": str(current_user_id)},
                room=room_name,
            )
            logger.info(f"Emitted group:member_left (leave) for user={current_user_id} group={group_id}")
        except Exception as exc:
            logger.warning(f"Failed to emit group:member_left (leave): {exc}")

