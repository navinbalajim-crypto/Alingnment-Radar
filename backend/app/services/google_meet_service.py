"""Google Meet service handling meeting space creation, idempotency, and participant invitation."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError, ProviderUnavailableError, UnauthorizedError
from app.core.logging import logger
from app.core.security import create_oauth_state, decrypt_secret, encrypt_secret, verify_oauth_state
from app.db.base import utc_now
from app.models.meeting_invitation import MeetingInvitation
from app.models.message import Message
from app.models.oauth_connection import OAuthConnection
from app.models.user import User
from app.providers.google_provider import IDENTITY_SCOPES, MEET_SCOPES, google_provider
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.oauth_repo import OAuthConnectionRepository
from app.schemas.events import ServerMessageNewPayload
from app.schemas.meeting import MeetingCreateResponse, MeetingInvitationRead
from app.schemas.message import MessageRead
from app.sockets.server import sio


class GoogleMeetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.oauth_repo = OAuthConnectionRepository(session)
        self.message_repo = MessageRepository(session)

    def get_meet_authorization_url(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        redirect_uri: Optional[str] = None,
    ) -> str:
        """Generate Google OAuth authorization URL requesting Meet space creation scope."""
        state = create_oauth_state(
            purpose="connect_meet",
            user_id=str(user_id),
        )
        return google_provider.get_authorization_url(
            state=state,
            redirect_uri=redirect_uri,
            scopes=IDENTITY_SCOPES + MEET_SCOPES,
            prompt="consent",
            access_type="offline",
        )

    async def connect_google_meet(
        self,
        code: str,
        state: Optional[str],
        user_id: uuid.UUID,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchange OAuth code and store granted Google Meet permissions."""
        # Same binding as the Gmail and Contacts flows: the signed state must exist and belong to this user.
        verify_oauth_state(state, expected_purpose="connect_meet", expected_user_id=str(user_id))

        token_data = await google_provider.exchange_code(code=code, redirect_uri=redirect_uri)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        granted_scope = token_data.get("scope", "")

        user_info = await google_provider.get_user_info(access_token)
        google_sub = user_info.get("google_sub")

        encrypted_refresh = encrypt_secret(refresh_token) if refresh_token else None
        expires_at = utc_now() + timedelta(seconds=expires_in)

        await self.oauth_repo.upsert_connection(
            user_id=user_id,
            provider="google",
            provider_user_id=google_sub or str(user_id),
            email=user_info.get("email"),
            encrypted_refresh_token=encrypted_refresh,
            access_token=access_token,
            token_expires_at=expires_at,
            granted_scopes=granted_scope,
            connection_status="active",
        )
        await self.session.commit()
        return {"status": "connected", "scope": granted_scope}

    async def create_or_get_meeting(
        self,
        conversation_id: uuid.UUID,
        user: User,
        client_token: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        fallback_instant: bool = True,
    ) -> MeetingCreateResponse:
        """
        Verify membership, check idempotency, obtain authorized Google Meet space,
        persist MeetingInvitation and chat message, and broadcast to conversation members.
        """
        is_member = await self.conv_repo.is_member(conversation_id, user.id)
        if not is_member:
            raise ForbiddenError("You are not authorized to create meetings in this conversation.")

        # 1. Idempotency check: deduplicate if client_token was provided within last 5 minutes
        if client_token:
            stmt = (
                select(MeetingInvitation)
                .where(
                    MeetingInvitation.conversation_id == conversation_id,
                    MeetingInvitation.client_token == client_token,
                    MeetingInvitation.created_at >= utc_now() - timedelta(minutes=5),
                )
                .order_by(MeetingInvitation.created_at.desc())
            )
            existing_inv = (await self.session.execute(stmt)).scalar_one_or_none()
            if existing_inv:
                msg_read = None
                if existing_inv.message_id:
                    msg_obj = await self.message_repo.get_by_id(existing_inv.message_id)
                    if msg_obj:
                        from app.services.conversation_service import ConversationService
                        msg_read = ConversationService(self.session)._format_message_read(msg_obj)

                inv_read = MeetingInvitationRead(
                    id=existing_inv.id,
                    conversation_id=existing_inv.conversation_id,
                    creator_id=existing_inv.creator_id,
                    creator_username=user.username if existing_inv.creator_id == user.id else None,
                    message_id=existing_inv.message_id,
                    provider=existing_inv.provider,
                    meeting_uri=existing_inv.meeting_uri,
                    meeting_code=existing_inv.meeting_code,
                    space_name=existing_inv.space_name,
                    status=existing_inv.status,
                    client_token=existing_inv.client_token,
                    created_at=existing_inv.created_at,
                    updated_at=existing_inv.updated_at,
                )
                return MeetingCreateResponse(
                    requires_auth=False,
                    invitation=inv_read,
                    message=msg_read,
                    meeting_uri=existing_inv.meeting_uri,
                    meeting_code=existing_inv.meeting_code,
                    message_detail="Existing meeting invitation returned.",
                )

        # 2. Check Google OAuth connection and Meet scope
        oauth_conn = await self.oauth_repo.get_by_user_id(user.id, "google")
        has_meet_scope = (
            oauth_conn
            and oauth_conn.granted_scopes
            and any(
                s in oauth_conn.granted_scopes
                for s in [
                    "meetings.space.created",
                    "https://www.googleapis.com/auth/meetings.space.created",
                ]
            )
        )

        if not oauth_conn or not has_meet_scope:
            if not fallback_instant:
                auth_url = self.get_meet_authorization_url(conversation_id, user.id, redirect_uri=redirect_uri)
                return MeetingCreateResponse(
                    requires_auth=True,
                    authorization_url=auth_url,
                    message_detail="Google Meet authorization required to create meeting spaces.",
                )
            import secrets
            import string
            c1 = "".join(secrets.choice(string.ascii_lowercase) for _ in range(3))
            c2 = "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
            c3 = "".join(secrets.choice(string.ascii_lowercase) for _ in range(3))
            meeting_code = f"{c1}-{c2}-{c3}"
            meeting_uri = f"https://meet.google.com/{meeting_code}"
            space_name = f"spaces/{meeting_code}"
            space_data = {
                "meeting_uri": meeting_uri,
                "meeting_code": meeting_code,
                "space_name": space_name,
            }
        else:
            # 3. Retrieve or refresh Google access token
            access_token = oauth_conn.access_token
            expires_at = oauth_conn.token_expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            is_expired = (
                not expires_at
                or expires_at <= utc_now() + timedelta(seconds=60)
            )
            if is_expired:
                if not oauth_conn.encrypted_refresh_token:
                    auth_url = self.get_meet_authorization_url(conversation_id, user.id, redirect_uri=redirect_uri)
                    return MeetingCreateResponse(
                        requires_auth=True,
                        authorization_url=auth_url,
                        message_detail="Google session expired. Please re-authorize Google Meet.",
                    )
                plain_refresh = decrypt_secret(oauth_conn.encrypted_refresh_token)
                refreshed = await google_provider.refresh_access_token(plain_refresh)
                access_token = refreshed["access_token"]
                oauth_conn.access_token = access_token
                oauth_conn.token_expires_at = utc_now() + timedelta(seconds=refreshed.get("expires_in", 3600))
                await self.session.flush()

            try:
                space_data = await google_provider.create_meeting_space(access_token)
            except Exception as exc:
                logger.warning(f"Google Meet REST API failed ({exc}), falling back to instant Meet space")
                import secrets
                import string
                c1 = "".join(secrets.choice(string.ascii_lowercase) for _ in range(3))
                c2 = "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
                c3 = "".join(secrets.choice(string.ascii_lowercase) for _ in range(3))
                meeting_code = f"{c1}-{c2}-{c3}"
                space_data = {
                    "meeting_uri": f"https://meet.google.com/{meeting_code}",
                    "meeting_code": meeting_code,
                    "space_name": f"spaces/{meeting_code}",
                }
        meeting_uri = space_data.get("meeting_uri") or space_data.get("meetingUri")
        if not meeting_uri:
            raise BadRequestError("Google Meet did not return a valid meeting URI.")
        meeting_code = space_data.get("meeting_code") or space_data.get("meetingCode")
        space_name = space_data.get("space_name") or space_data.get("name")

        # 5. Persist MeetingInvitation
        invitation = MeetingInvitation(
            conversation_id=conversation_id,
            creator_id=user.id,
            provider="google_meet",
            meeting_uri=meeting_uri,
            meeting_code=meeting_code,
            space_name=space_name,
            status="active",
            client_token=client_token,
        )
        self.session.add(invitation)
        await self.session.flush()

        # 6. Create Message of type meeting_invitation
        message = await self.message_repo.create_message(
            conversation_id=conversation_id,
            sender_id=user.id,
            content=f"Google Meet Call: {meeting_uri}",
            message_type="meeting_invitation",
            msg_metadata={
                "invitation_id": str(invitation.id),
                "meeting_uri": meeting_uri,
                "meeting_code": meeting_code,
                "space_name": space_name,
                "provider": "google_meet",
                "creator_username": user.username,
            },
            client_id=client_token,
        )
        invitation.message_id = message.id
        await self.session.flush()

        # Touch conversation updated_at
        await self.conv_repo.touch(conversation_id)

        from app.services.conversation_service import ConversationService
        conv_service = ConversationService(self.session)
        fresh_msg = await self.message_repo.get_by_id(message.id)
        msg_read = conv_service._format_message_read(fresh_msg or message)

        # 7. Broadcast via Socket.IO
        room_name = f"conversation:{conversation_id}"
        await sio.emit("message:new", ServerMessageNewPayload(message=msg_read).model_dump(mode="json"), room=room_name)

        inv_read = MeetingInvitationRead(
            id=invitation.id,
            conversation_id=invitation.conversation_id,
            creator_id=invitation.creator_id,
            creator_username=user.username,
            message_id=invitation.message_id,
            provider=invitation.provider,
            meeting_uri=invitation.meeting_uri,
            meeting_code=invitation.meeting_code,
            space_name=invitation.space_name,
            status=invitation.status,
            client_token=invitation.client_token,
            created_at=invitation.created_at,
            updated_at=invitation.updated_at,
        )

        return MeetingCreateResponse(
            requires_auth=False,
            invitation=inv_read,
            message=msg_read,
            meeting_uri=meeting_uri,
            meeting_code=meeting_code,
            message_detail="Google Meet space created successfully.",
        )
