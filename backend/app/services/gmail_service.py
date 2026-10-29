"""Gmail notification service managing Gmail metadata integration and in-app mail alerts."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import BadRequestError, RateLimitError, UnauthorizedError
from app.core.logging import logger
from app.core.security import (
    create_oauth_state,
    decrypt_secret,
    encrypt_secret,
    generate_pkce_pair,
    rate_limiter,
    verify_oauth_state,
)
from app.db.base import utc_now
from app.models.oauth_connection import OAuthConnection
from app.providers.google_provider import GMAIL_SCOPES, IDENTITY_SCOPES, google_provider
from app.repositories.gmail_repo import GmailNotificationRepository
from app.repositories.oauth_repo import OAuthConnectionRepository
from app.schemas.oauth import (
    GmailCheckResponse,
    GmailNotificationItem,
    GmailNotificationListResponse,
    GmailStatusResponse,
    GoogleAuthUrlResponse,
)


class GmailNotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.gmail_repo = GmailNotificationRepository(session)
        self.oauth_repo = OAuthConnectionRepository(session)

    async def _get_active_gmail_connection(self, user_id: uuid.UUID) -> OAuthConnection:
        """Find active Google Gmail connection for user."""
        conn = await self.oauth_repo.get_by_user_id(user_id, "google_gmail")
        if conn:
            if conn.connection_status == "active":
                return conn
            elif conn.connection_status == "error":
                raise UnauthorizedError("Gmail connection has expired or been revoked. Please reconnect Gmail in Settings.")

        # Fallback check if primary google connection has gmail scope
        conn = await self.oauth_repo.get_by_user_id(user_id, "google")
        if conn and conn.connection_status == "active" and "gmail" in (conn.granted_scopes or ""):
            return conn

        raise BadRequestError(
            "Gmail notifications are not connected. Please connect your Gmail account in Settings to enable email alerts."
        )

    async def _ensure_valid_google_access_token(self, connection: OAuthConnection) -> str:
        """Ensure connection has an unexpired access token, refreshing if necessary."""
        now = utc_now()
        expires_at = connection.token_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        is_expired = not connection.access_token or (
            expires_at is not None and expires_at <= now + timedelta(seconds=60)
        )

        if not is_expired:
            return connection.access_token

        if not connection.encrypted_refresh_token:
            if connection.provider != "google":
                primary = await self.oauth_repo.get_by_user_id(connection.user_id, "google")
                if primary and primary.encrypted_refresh_token:
                    connection.encrypted_refresh_token = primary.encrypted_refresh_token

        if not connection.encrypted_refresh_token:
            raise UnauthorizedError("Gmail access token has expired and no refresh token is stored. Please reconnect Gmail.")

        plain_refresh_token = decrypt_secret(connection.encrypted_refresh_token)
        new_token_data = await google_provider.refresh_access_token(plain_refresh_token)

        new_access_token = new_token_data.get("access_token")
        expires_in = new_token_data.get("expires_in", 3600)

        connection.access_token = new_access_token
        connection.token_expires_at = now + timedelta(seconds=expires_in)
        connection.updated_at = now
        await self.session.flush()

        return new_access_token

    def get_connect_url(
        self,
        user_id: uuid.UUID,
        redirect_uri: Optional[str] = None,
    ) -> GoogleAuthUrlResponse:
        """Generate Google OAuth authorization URL for Gmail metadata access with PKCE.

        Includes IDENTITY_SCOPES alongside GMAIL_SCOPES: the token this flow produces is used
        immediately afterwards (in connect_gmail_with_code) to call Google's userinfo endpoint
        to resolve the connected email address, and that endpoint requires openid/email/profile
        scope. Requesting gmail.metadata alone made every connection attempt fail at that step
        with a generic "invalid or expired token" error, right after the user had already
        granted consent -- not an API-enablement or account-permission problem, just a missing
        scope in this request.
        """
        code_verifier, code_challenge = generate_pkce_pair()
        state = create_oauth_state(purpose="gmail", user_id=str(user_id), code_verifier=code_verifier)
        url = google_provider.get_authorization_url(
            state=state,
            redirect_uri=redirect_uri,
            prompt="consent",
            scopes=IDENTITY_SCOPES + GMAIL_SCOPES,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            access_type="offline",
        )
        return GoogleAuthUrlResponse(url=url, state=state)

    async def connect_gmail_with_code(
        self,
        user_id: uuid.UUID,
        code: str,
        state: str,
        redirect_uri: Optional[str] = None,
    ) -> GmailStatusResponse:
        """Exchange authorization code specifically for Gmail integration and bind to authenticated user."""
        state_payload = verify_oauth_state(state, expected_purpose="gmail", expected_user_id=str(user_id))
        code_verifier = state_payload.get("code_verifier")

        token_data = await google_provider.exchange_code(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        granted_scope = token_data.get("scope", "")

        if not access_token:
            raise BadRequestError("Google token exchange did not return an access token.")

        if "gmail" not in granted_scope:
            raise UnauthorizedError(
                "Gmail metadata permission was not granted by user. Please accept the Gmail permission on the consent screen."
            )

        user_info = await google_provider.get_user_info(access_token)
        google_sub = user_info.get("google_sub") or str(user_id)
        email = user_info.get("email")

        encrypted_refresh = encrypt_secret(refresh_token) if refresh_token else None
        expires_at = utc_now() + timedelta(seconds=expires_in)

        if not encrypted_refresh:
            existing = await self.oauth_repo.get_by_user_id(user_id, "google_gmail")
            if existing and existing.encrypted_refresh_token:
                encrypted_refresh = existing.encrypted_refresh_token
            else:
                existing_login = await self.oauth_repo.get_by_user_id(user_id, "google")
                if existing_login and existing_login.encrypted_refresh_token:
                    encrypted_refresh = existing_login.encrypted_refresh_token

        conn = await self.oauth_repo.upsert_connection(
            user_id=user_id,
            provider="google_gmail",
            provider_user_id=google_sub,
            email=email,
            encrypted_refresh_token=encrypted_refresh,
            access_token=access_token,
            token_expires_at=expires_at,
            granted_scopes=granted_scope,
            connection_status="active",
        )

        # Trigger non-blocking initial check
        unread_count = 0
        try:
            check_res = await self.check_gmail_notifications(user_id, bypass_rate_limit=True)
            unread_count = check_res.unread_count
        except Exception as exc:
            logger.warning(f"Initial Gmail check after connect failed: {exc}")

        return GmailStatusResponse(
            connected=True,
            provider="google_gmail",
            email=conn.email,
            granted_scopes=conn.granted_scopes,
            connected_at=conn.created_at,
            last_checked_at=conn.updated_at,
            unread_notifications_count=unread_count,
            polling_interval_seconds=60,
            delivery_mechanism="polling",
        )

    async def get_status(self, user_id: uuid.UUID) -> GmailStatusResponse:
        """Retrieve Gmail notification connection status and unread count."""
        conn = await self.oauth_repo.get_by_user_id(user_id, "google_gmail")
        if not conn or conn.connection_status != "active":
            # Fallback check
            conn = await self.oauth_repo.get_by_user_id(user_id, "google")
            if not conn or conn.connection_status != "active" or "gmail" not in (conn.granted_scopes or ""):
                return GmailStatusResponse(
                    connected=False,
                    provider="google_gmail",
                    unread_notifications_count=0,
                    delivery_mechanism="polling",
                )

        unread_count = await self.gmail_repo.count_by_user(user_id, unread_only=True)
        return GmailStatusResponse(
            connected=True,
            provider="google_gmail",
            email=conn.email,
            granted_scopes=conn.granted_scopes,
            connected_at=conn.created_at,
            last_checked_at=conn.updated_at,
            unread_notifications_count=unread_count,
            polling_interval_seconds=60,
            delivery_mechanism="polling",
        )

    async def check_gmail_notifications(
        self,
        user_id: uuid.UUID,
        bypass_rate_limit: bool = False,
    ) -> GmailCheckResponse:
        """
        Poll Gmail API for recent messages, fetch headers only, deduplicate against stored alerts,
        and save in-app notifications. Rate-limited to protect user quotas.
        """
        if not bypass_rate_limit:
            # Max 3 checks per 30 seconds per user
            rate_limiter.enforce(
                key=f"gmail_check_{user_id}",
                max_attempts=3,
                window_seconds=30,
                action_name="Gmail check",
            )

        conn = await self._get_active_gmail_connection(user_id)
        access_token = await self._ensure_valid_google_access_token(conn)

        # 1. Fetch recent message IDs (max 15 stubs)
        try:
            messages_data = await google_provider.fetch_gmail_messages(access_token, max_results=15)
        except UnauthorizedError:
            conn.connection_status = "error"
            await self.session.flush()
            raise
        raw_messages = messages_data.get("messages", [])
        if not raw_messages:
            conn.updated_at = utc_now()
            await self.session.flush()
            unread_count = await self.gmail_repo.count_by_user(user_id, unread_only=True)
            return GmailCheckResponse(
                new_notifications_count=0,
                unread_count=unread_count,
                message="No recent Gmail messages found.",
            )

        candidate_ids = [m["id"] for m in raw_messages if "id" in m]
        existing_ids = await self.gmail_repo.get_existing_message_ids(user_id, candidate_ids)
        new_ids = [mid for mid in candidate_ids if mid not in existing_ids]

        # 2. For newly discovered messages, fetch minimal headers (max 10 to limit API calls)
        created_count = 0
        items_to_create: List[Dict[str, Any]] = []

        for msg_id in new_ids[:10]:
            try:
                meta = await google_provider.fetch_gmail_message_metadata(access_token, msg_id)
                received_dt = None
                if meta.get("internal_date_ms"):
                    received_dt = datetime.fromtimestamp(meta["internal_date_ms"] / 1000.0, tz=timezone.utc)

                items_to_create.append({
                    "gmail_message_id": meta["message_id"],
                    "gmail_thread_id": meta.get("thread_id"),
                    "sender": meta.get("sender"),
                    "subject": meta.get("subject"),
                    "snippet": meta.get("snippet"),
                    "received_at": received_dt or utc_now(),
                })
            except Exception as e:
                logger.warning(f"Failed to fetch metadata for Gmail message {msg_id}: {e}")

        if items_to_create:
            created_count = await self.gmail_repo.bulk_create_notifications(user_id, items_to_create)

        conn.updated_at = utc_now()
        await self.session.flush()

        unread_count = await self.gmail_repo.count_by_user(user_id, unread_only=True)
        return GmailCheckResponse(
            new_notifications_count=created_count,
            unread_count=unread_count,
            message=(
                f"Checked Gmail. Found {created_count} new email notification(s)."
                if created_count > 0
                else "Checked Gmail. Inbox is up to date."
            ),
        )

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> GmailNotificationListResponse:
        """List in-app Gmail notifications with minimal metadata."""
        records = await self.gmail_repo.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )
        total = await self.gmail_repo.count_by_user(user_id, unread_only=False)
        unread = await self.gmail_repo.count_by_user(user_id, unread_only=True)

        items = [
            GmailNotificationItem(
                id=r.id,
                gmail_message_id=r.gmail_message_id,
                gmail_thread_id=r.gmail_thread_id,
                sender=r.sender,
                subject=r.subject,
                snippet=r.snippet,
                received_at=r.received_at,
                is_read=r.is_read,
                created_at=r.created_at,
            )
            for r in records
        ]

        return GmailNotificationListResponse(
            notifications=items,
            unread_count=unread,
            total_count=total,
        )

    async def mark_as_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        """Mark a single Gmail notification as read."""
        return await self.gmail_repo.mark_as_read(notification_id, user_id)

    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        """Mark all unread Gmail notifications as read for current user."""
        return await self.gmail_repo.mark_all_as_read(user_id)

    async def disconnect_gmail(self, user_id: uuid.UUID) -> None:
        """Disconnect Gmail integration without disconnecting Google Contacts or revoking app session."""
        await self.oauth_repo.delete_by_user(user_id, "google_gmail")
        for prov in ["google", "google_contacts"]:
            other_conn = await self.oauth_repo.get_by_user_id(user_id, prov)
            if other_conn and other_conn.granted_scopes and "gmail" in other_conn.granted_scopes:
                scopes = [s for s in other_conn.granted_scopes.split() if "gmail" not in s]
                other_conn.granted_scopes = " ".join(scopes)
                await self.session.flush()

        logger.info(f"User {user_id} disconnected Gmail notifications integration.")
