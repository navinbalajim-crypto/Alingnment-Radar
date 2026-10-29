"""Contacts service managing Google contacts synchronization and colleague matching."""

import uuid
from datetime import timedelta, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import BadRequestError, UnauthorizedError
from app.core.logging import logger
from app.core.security import decrypt_secret, normalize_email
from app.db.base import utc_now
from app.models.oauth_connection import OAuthConnection
from app.providers.google_provider import google_provider
from app.repositories.contact_repo import UserContactRepository
from app.repositories.oauth_repo import OAuthConnectionRepository
from app.repositories.user_repo import UserRepository
from app.schemas.contact import ContactItem, ContactListResponse, SyncContactsResponse


class ContactService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_repo = UserContactRepository(session)
        self.oauth_repo = OAuthConnectionRepository(session)
        self.user_repo = UserRepository(session)

    async def _get_active_contacts_connection(self, user_id: uuid.UUID) -> OAuthConnection:
        """Find active Google Contacts connection, checking dedicated provider first, then primary google connection."""
        conn = await self.oauth_repo.get_by_user_id(user_id, "google_contacts")
        if conn:
            if conn.connection_status == "active":
                return conn
            elif conn.connection_status == "error":
                raise UnauthorizedError("Google Contacts connection has expired or been revoked. Please reconnect in Settings.")

        # Fallback to primary google connection if contacts scope was granted
        conn = await self.oauth_repo.get_by_user_id(user_id, "google")
        if conn and conn.connection_status == "active" and "contacts" in (conn.granted_scopes or ""):
            return conn

        raise BadRequestError(
            "Google Contacts is not connected. Please connect your Google account in Settings to enable teammate discovery."
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
            # Check if primary google connection has refresh token
            if connection.provider != "google":
                primary = await self.oauth_repo.get_by_user_id(connection.user_id, "google")
                if primary and primary.encrypted_refresh_token:
                    connection.encrypted_refresh_token = primary.encrypted_refresh_token

        if not connection.encrypted_refresh_token:
            raise UnauthorizedError("Google access credentials have expired and no refresh token is stored. Please reconnect Google.")

        plain_refresh_token = decrypt_secret(connection.encrypted_refresh_token)
        try:
            new_token_data = await google_provider.refresh_access_token(plain_refresh_token)
        except UnauthorizedError:
            connection.connection_status = "error"
            await self.session.flush()
            raise

        new_access_token = new_token_data.get("access_token")
        expires_in = new_token_data.get("expires_in", 3600)

        connection.access_token = new_access_token
        connection.token_expires_at = now + timedelta(seconds=expires_in)
        connection.updated_at = now
        await self.session.flush()

        return new_access_token

    async def sync_google_contacts(self, user_id: uuid.UUID) -> SyncContactsResponse:
        """
        Fetch contacts from Google People API with pagination, match against registered users,
        and store ONLY registered teammate contacts for privacy.
        """
        conn = await self._get_active_contacts_connection(user_id)
        access_token = await self._ensure_valid_google_access_token(conn)

        raw_contacts = await google_provider.fetch_contacts(access_token, page_size=100, max_contacts=1000)

        # Normalize emails and find registered platform teammates
        contact_emails = [
            normalize_email(c["contact_email"])
            for c in raw_contacts
            if c.get("contact_email")
        ]
        matched_users = await self.user_repo.get_users_by_normalized_emails(contact_emails)
        # Exclude self
        teammate_matches = [u for u in matched_users if u.id != user_id]
        matched_email_set = {u.email for u in teammate_matches}

        # Privacy gate: retain and persist ONLY contacts who are registered app users
        registered_contacts_data = [
            c for c in raw_contacts
            if normalize_email(c.get("contact_email", "")) in matched_email_set
        ]

        upserted_count = await self.contact_repo.sync_matched_contacts(user_id, registered_contacts_data)

        conn.updated_at = utc_now()
        await self.session.flush()

        logger.info(
            f"User {user_id}: scanned {len(raw_contacts)} Google contacts, matched and retained {upserted_count} registered teammates."
        )

        return SyncContactsResponse(
            synced_count=len(raw_contacts),
            matched_registered_count=upserted_count,
            message=(
                f"Scanned {len(raw_contacts)} contacts from Google. "
                f"Found {upserted_count} teammate(s) already registered on Alignment Radar."
            ),
        )

    async def list_user_contacts(
        self,
        user_id: uuid.UUID,
        query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ContactListResponse:
        """List authenticated user's address book contacts, displaying only registered app teammates."""
        contacts = await self.contact_repo.get_contacts_by_user(
            user_id=user_id,
            query=query,
            limit=limit,
            offset=offset,
        )

        emails = [c.contact_email_normalized for c in contacts]
        matched_users = await self.user_repo.get_users_by_normalized_emails(emails)
        user_lookup = {u.email: u for u in matched_users if u.id != user_id}

        items: List[ContactItem] = []
        for c in contacts:
            reg_user = user_lookup.get(c.contact_email_normalized)
            # Only display contacts who are verified registered users
            if not reg_user:
                continue

            items.append(
                ContactItem(
                    id=c.id,
                    contact_email=c.contact_email,
                    contact_name=c.contact_name or reg_user.display_name or reg_user.username,
                    is_registered=True,
                    registered_username=reg_user.username,
                    registered_user_id=reg_user.id,
                    avatar_url=reg_user.avatar_url,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
            )

        items.sort(key=lambda item: (item.contact_name or item.contact_email).lower())

        return ContactListResponse(contacts=items, total=len(items))
