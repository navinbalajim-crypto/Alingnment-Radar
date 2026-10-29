"""Group invitation service managing token creation, verification, and onboarding."""

import uuid
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_registration_ticket,
    generate_otp_code,
    generate_secure_token,
    hash_otp_code,
    hash_token,
    normalize_email,
    rate_limiter,
    validate_username_format,
    verify_otp_code,
    verify_registration_ticket,
)
from app.db.base import utc_now
from app.models.invitation import GroupInvitation
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.invitation_repo import InvitationRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.repositories.verification_repo import VerificationRepository
from app.schemas.auth import (
    RequestCodeResponse,
    TokenResponse,
    UserTokenPayload,
)
from app.schemas.events import GroupMemberJoinedPayload
from app.schemas.group import InvitationResponse
from app.schemas.invitation import (
    InvitationPreviewResponse,
    InvitationVerifyCodeResponse,
)
from app.services.auth_service import AuthService
from app.services.email_service import email_service


class InvitationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.invitation_repo = InvitationRepository(session)
        self.conv_repo = ConversationRepository(session)
        self.user_repo = UserRepository(session)
        self.verification_repo = VerificationRepository(session)
        self.session_repo = SessionRepository(session)
        self.auth_service = AuthService(session)

    async def create_invitation(
        self,
        group_id: uuid.UUID,
        current_user_id: uuid.UUID,
        max_uses: Optional[int] = None,
        expires_in_days: int = 7,
    ) -> InvitationResponse:
        conv = await self.conv_repo.get_by_id(group_id)
        if not conv or not conv.is_group:
            raise NotFoundError("Group not found.")

        # Check that user is an admin of this group
        member = await self.conv_repo.get_member(group_id, current_user_id)
        if not member or member.role != "admin":
            raise ForbiddenError("Only group admins can create invitations.")

        token = generate_secure_token(32)
        token_hash = hash_token(token)
        expires_at = utc_now() + timedelta(days=expires_in_days)

        invitation = await self.invitation_repo.create_invitation(
            group_id=group_id,
            created_by_id=current_user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            max_uses=max_uses,
        )

        base_origin = settings.FRONTEND_ORIGINS[0].rstrip("/") if settings.FRONTEND_ORIGINS else "http://localhost:5173"
        invitation_url = f"{base_origin}/invitations/{token}"

        return InvitationResponse(
            id=invitation.id,
            group_id=invitation.group_id,
            invitation_url=invitation_url,
            token=token,
            max_uses=invitation.max_uses,
            uses_count=invitation.uses_count,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )

    async def revoke_invitation(
        self, group_id: uuid.UUID, invitation_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> None:
        member = await self.conv_repo.get_member(group_id, current_user_id)
        if not member or member.role != "admin":
            raise ForbiddenError("Only group admins can revoke invitations.")

        invitation = await self.invitation_repo.get_by_id(invitation_id)
        if not invitation or invitation.group_id != group_id:
            raise NotFoundError("Invitation not found.")

        await self.invitation_repo.revoke_invitation(invitation)

    async def preview_invitation(self, token: str) -> InvitationPreviewResponse:
        token_hash = hash_token(token)
        invitation = await self.invitation_repo.get_by_token_hash(token_hash)

        if not invitation or not invitation.group:
            raise NotFoundError("Invalid invitation link.")

        is_valid = invitation.is_valid()
        group_title = invitation.group.title or "Untitled Group"
        invited_by = invitation.created_by.username if invitation.created_by else "Admin"

        return InvitationPreviewResponse(
            group_id=invitation.group_id,
            group_title=group_title,
            invited_by_username=invited_by,
            is_valid=is_valid,
            expires_at=invitation.expires_at,
        )

    async def request_invitation_code(self, token: str, raw_email: str) -> RequestCodeResponse:
        email = normalize_email(raw_email)
        token_hash = hash_token(token)
        invitation = await self.invitation_repo.get_by_token_hash(token_hash)

        if not invitation or not invitation.is_valid():
            raise BadRequestError("This invitation link is invalid, expired, or has reached its usage limit.")

        rate_limiter.enforce(f"otp:invite:{email}", max_attempts=settings.OTP_MAX_ATTEMPTS, window_seconds=600, action_name="invitation code request")
        rate_limiter.enforce(f"otp:cooldown:{email}", max_attempts=1, window_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS, action_name="resend")

        code = generate_otp_code()
        hashed_code = hash_otp_code(code)
        expires_at = utc_now() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

        await self.verification_repo.create_challenge(
            email=email,
            hashed_code=hashed_code,
            purpose="invitation",
            invitation_id=invitation.id,
            expires_at=expires_at,
            max_attempts=settings.OTP_MAX_ATTEMPTS,
        )

        group_title = invitation.group.title if invitation.group else "Group"
        await email_service.send_invitation_code(email=email, code=code, group_title=group_title)

        return RequestCodeResponse(
            message=f"Verification code sent to {email}.",
            email=email,
            cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )

    async def verify_invitation_code(
        self,
        token: str,
        raw_email: str,
        code: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> InvitationVerifyCodeResponse:
        email = normalize_email(raw_email)
        token_hash = hash_token(token)
        invitation = await self.invitation_repo.get_by_token_hash(token_hash)

        if not invitation or not invitation.is_valid():
            raise BadRequestError("This invitation link is invalid or expired.")

        challenge = await self.verification_repo.get_latest_active_challenge(
            email=email,
            purpose="invitation",
            invitation_id=invitation.id,
        )

        if not challenge or challenge.is_expired():
            raise BadRequestError("Verification code has expired or is invalid. Please request a new code.")

        if challenge.has_exceeded_attempts():
            raise BadRequestError("Maximum attempts exceeded. Please request a new code.")

        if not verify_otp_code(code, challenge.hashed_code):
            attempts = await self.verification_repo.increment_attempts(challenge)
            remaining = max(0, challenge.max_attempts - attempts)
            raise BadRequestError(f"Invalid verification code. {remaining} attempt(s) remaining.")

        await self.verification_repo.mark_consumed(challenge)

        existing_user = await self.user_repo.get_by_email(email)
        group_title = invitation.group.title if invitation.group else "Group"

        if existing_user:
            # Check if already a member
            is_member = await self.conv_repo.is_member(invitation.group_id, existing_user.id)
            if not is_member:
                # Add to group
                member = await self.conv_repo.add_member(invitation.group_id, existing_user.id, role="member")
                await self.invitation_repo.increment_uses(invitation)

                # Emit real-time notification to group room so existing members refresh
                try:
                    from app.sockets.server import sio
                    from app.db.base import utc_now
                    joined_payload = GroupMemberJoinedPayload(
                        group_id=invitation.group_id,
                        user_id=existing_user.id,
                        username=existing_user.username,
                        display_name=existing_user.display_name,
                        role="member",
                        joined_at=member.joined_at or utc_now(),
                    )
                    await sio.emit(
                        "group:member_joined",
                        joined_payload.model_dump(mode="json"),
                        room=f"conversation:{invitation.group_id}",
                    )
                    logger.info(f"Emitted group:member_joined for user={existing_user.id} group={invitation.group_id}")
                except Exception as exc:
                    logger.warning(f"Failed to emit group:member_joined: {exc}")
            else:
                await self.invitation_repo.increment_uses(invitation)

            # Issue session
            tokens = await self.auth_service._create_tokens_for_user(
                existing_user, user_agent=user_agent, ip_address=ip_address
            )

            return InvitationVerifyCodeResponse(
                message=f"Joined '{group_title}' successfully.",
                is_existing_user=True,
                group_id=invitation.group_id,
                group_title=group_title,
                tokens=tokens,
            )
        else:
            # Issue registration ticket for new user onboarding
            ticket = create_registration_ticket(email=email)
            return InvitationVerifyCodeResponse(
                message="Email verified. Please complete registration to join the group.",
                is_existing_user=False,
                group_id=invitation.group_id,
                group_title=group_title,
                registration_ticket=ticket,
            )

    async def complete_invitation_registration(
        self,
        token: str,
        registration_ticket: str,
        raw_username: str,
        display_name: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        token_hash = hash_token(token)
        invitation = await self.invitation_repo.get_by_token_hash(token_hash)
        if not invitation or not invitation.is_valid():
            raise BadRequestError("Invitation link is invalid or expired.")

        verified_email = verify_registration_ticket(registration_ticket)

        try:
            valid_username = validate_username_format(raw_username)
        except ValueError as exc:
            raise BadRequestError(str(exc))

        is_taken = await self.user_repo.is_username_taken(valid_username)
        if is_taken:
            raise ConflictError("Username is already taken.")

        # Create user
        user = await self.user_repo.create_user(
            email=verified_email,
            username=valid_username,
            display_name=display_name,
        )

        # Add to group
        member = await self.conv_repo.add_member(invitation.group_id, user.id, role="member")
        await self.invitation_repo.increment_uses(invitation)

        # Emit real-time notification to group room
        try:
            from app.sockets.server import sio
            from app.db.base import utc_now
            joined_payload = GroupMemberJoinedPayload(
                group_id=invitation.group_id,
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                role="member",
                joined_at=member.joined_at or utc_now(),
            )
            await sio.emit(
                "group:member_joined",
                joined_payload.model_dump(mode="json"),
                room=f"conversation:{invitation.group_id}",
            )
            logger.info(f"Emitted group:member_joined for new user={user.id} group={invitation.group_id}")
        except Exception as exc:
            logger.warning(f"Failed to emit group:member_joined for new user: {exc}")

        return await self.auth_service._create_tokens_for_user(
            user, user_agent=user_agent, ip_address=ip_address
        )
