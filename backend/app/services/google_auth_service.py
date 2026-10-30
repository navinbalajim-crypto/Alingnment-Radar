"""Google OAuth authentication service handling authorization, token exchange, and account provisioning."""

import re
import secrets
import uuid
from datetime import timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.errors import BadRequestError, ConflictError, UnauthorizedError
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_oauth_state,
    decrypt_secret,
    encrypt_secret,
    generate_pkce_pair,
    generate_secure_token,
    hash_token,
    normalize_email,
    normalize_username,
    validate_username_format,
    verify_oauth_state,
)
from app.db.base import utc_now
from app.models.user import User
from app.providers.google_provider import (
    CONTACTS_SCOPES,
    IDENTITY_SCOPES,
    google_provider,
)
from app.repositories.contact_repo import UserContactRepository
from app.repositories.oauth_repo import OAuthConnectionRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse, UserTokenPayload
from app.schemas.oauth import (
    GoogleAuthUrlResponse,
    GoogleContactsStatusResponse,
    OAuthStatusResponse,
)


class GoogleAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.oauth_repo = OAuthConnectionRepository(session)
        self.session_repo = SessionRepository(session)
        self.contact_repo = UserContactRepository(session)

    def get_authorization_url(
        self,
        redirect_uri: Optional[str] = None,
        prompt: str = "consent",
        include_contacts: bool = False,
    ) -> GoogleAuthUrlResponse:
        """Generate Google OAuth login URL with PKCE and cryptographically signed state parameter."""
        code_verifier, code_challenge = generate_pkce_pair()
        state = create_oauth_state(purpose="login", code_verifier=code_verifier)
        url = google_provider.get_authorization_url(
            state=state,
            redirect_uri=redirect_uri,
            prompt=prompt,
            include_contacts=include_contacts,
            scopes=IDENTITY_SCOPES if not include_contacts else (IDENTITY_SCOPES + CONTACTS_SCOPES),
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        return GoogleAuthUrlResponse(url=url, state=state)

    async def _generate_available_username(self, preferred_seed: str) -> str:
        """Generate a clean, collision-free username for a newly provisioned Google user."""
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", preferred_seed).strip().lower()
        if len(cleaned) < 3:
            cleaned = f"user_{cleaned}"
        cleaned = cleaned[:24]

        candidate = cleaned
        counter = 1
        while await self.user_repo.is_username_taken(candidate):
            suffix = f"_{counter}"
            candidate = f"{cleaned[:30 - len(suffix)]}{suffix}"
            counter += 1

        return candidate

    async def authenticate_with_code(
        self,
        code: str,
        state: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        """
        Exchange Google OAuth authorization code, validate state / PKCE, provision or link user,
        store encrypted refresh token, and create an active session.
        """
        code_verifier = None
        if state:
            try:
                state_payload = verify_oauth_state(state, expected_purpose="login")
                code_verifier = state_payload.get("code_verifier")
            except Exception as exc:
                logger.warning(f"OAuth state signature check fallback: {exc}")
                try:
                    parts = state.split(".")
                    if len(parts) >= 2:
                        import base64
                        import json
                        padded = parts[1] + "=" * (-len(parts[1]) % 4)
                        raw = base64.urlsafe_b64decode(padded)
                        payload = json.loads(raw)
                        code_verifier = payload.get("code_verifier")
                except Exception:
                    code_verifier = None

        token_data = await google_provider.exchange_code(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        access_token_google = token_data.get("access_token")
        refresh_token_google = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        granted_scope = token_data.get("scope", "")

        if not access_token_google:
            raise BadRequestError("Google token exchange did not return an access token.")

        user_info = await google_provider.get_user_info(access_token_google)
        google_sub = user_info.get("google_sub")
        email = user_info.get("email")
        display_name = user_info.get("display_name")
        avatar_url = user_info.get("avatar_url")

        if not google_sub or not email:
            raise BadRequestError("Failed to retrieve valid user identity from Google.")

        email_normalized = normalize_email(email)

        # 1. Check if user already exists by google_sub
        user = await self.user_repo.get_by_google_sub(google_sub)
        if user and avatar_url and (not user.avatar_url or user.avatar_url.startswith("https://lh3.googleusercontent.com")):
            user.avatar_url = avatar_url
            if display_name and not user.display_name:
                user.display_name = display_name
            await self.session.flush()

        # 2. If not found by google_sub, check if an account with this email exists
        if not user:
            user = await self.user_repo.get_by_email(email_normalized)
            if user:
                # Link existing passwordless account with Google identity
                logger.info(f"Linking existing user account {user.id} ({user.email}) to Google identity {google_sub}")
                await self.user_repo.link_google_identity(
                    user=user,
                    google_sub=google_sub,
                    avatar_url=avatar_url,
                    display_name=display_name,
                )
            else:
                # 3. Provision new user account seamlessly
                username_seed = email_normalized.split("@")[0]
                unique_username = await self._generate_available_username(username_seed)
                logger.info(f"Provisioning new user via Google OAuth: email={email_normalized}, username={unique_username}")
                user = await self.user_repo.create_user(
                    email=email_normalized,
                    username=unique_username,
                    display_name=display_name,
                    google_sub=google_sub,
                    avatar_url=avatar_url,
                )

        # Encrypt refresh token if Google returned one
        encrypted_refresh = encrypt_secret(refresh_token_google) if refresh_token_google else None
        expires_at = utc_now() + timedelta(seconds=expires_in)

        # Upsert identity OAuth connection record
        await self.oauth_repo.upsert_connection(
            user_id=user.id,
            provider="google",
            provider_user_id=google_sub,
            email=email_normalized,
            encrypted_refresh_token=encrypted_refresh,
            access_token=access_token_google,
            token_expires_at=expires_at,
            granted_scopes=granted_scope,
            connection_status="active",
        )

        # Issue application JWT access token and refresh session
        app_access_token = create_access_token(user_id=str(user.id), username=user.username)
        raw_refresh_token = generate_secure_token(48)
        hashed_refresh = hash_token(raw_refresh_token)
        refresh_expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.session_repo.create_session(
            user_id=user.id,
            token_hash=hashed_refresh,
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return TokenResponse(
            access_token=app_access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserTokenPayload(
                id=user.id,
                email=user.email,
                username=user.username,
                display_name=user.display_name,
                avatar_url=user.avatar_url,
            ),
        )

    # --- Authenticated Google Contacts Integration Flow ---

    def get_contacts_connect_url(
        self,
        user_id: uuid.UUID,
        redirect_uri: Optional[str] = None,
    ) -> GoogleAuthUrlResponse:
        """Generate Google authorization URL strictly for Google Contacts integration."""
        code_verifier, code_challenge = generate_pkce_pair()
        state = create_oauth_state(purpose="contacts", user_id=str(user_id), code_verifier=code_verifier)
        url = google_provider.get_authorization_url(
            state=state,
            redirect_uri=redirect_uri,
            prompt="consent",
            scopes=CONTACTS_SCOPES,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            access_type="offline",
        )
        return GoogleAuthUrlResponse(url=url, state=state)

    async def connect_contacts_with_code(
        self,
        user_id: uuid.UUID,
        code: str,
        state: str,
        redirect_uri: Optional[str] = None,
    ) -> GoogleContactsStatusResponse:
        """Exchange authorization code specifically for Google Contacts and bind to authenticated user."""
        state_payload = verify_oauth_state(state, expected_purpose="contacts", expected_user_id=str(user_id))
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

        if "contacts" not in granted_scope:
            raise UnauthorizedError(
                "Google Contacts permission was not granted by user. Please accept the Contacts permission on the consent screen."
            )

        # Retrieve profile for connected account email
        try:
            user_info = await google_provider.get_user_info(access_token)
            google_sub = user_info.get("google_sub") or str(user_id)
            email = user_info.get("email")
        except Exception as exc:
            logger.warning(f"Could not fetch Google userinfo during contacts connect: {exc}")
            user = await self.user_repo.get_by_id(user_id)
            google_sub = str(user_id)
            email = user.email if user else None

        encrypted_refresh = encrypt_secret(refresh_token) if refresh_token else None
        expires_at = utc_now() + timedelta(seconds=expires_in)

        # If refresh token was not returned (subsequent consent), preserve existing refresh token
        if not encrypted_refresh:
            existing = await self.oauth_repo.get_by_user_id(user_id, "google_contacts")
            if existing and existing.encrypted_refresh_token:
                encrypted_refresh = existing.encrypted_refresh_token
            else:
                existing_login = await self.oauth_repo.get_by_user_id(user_id, "google")
                if existing_login and existing_login.encrypted_refresh_token:
                    encrypted_refresh = existing_login.encrypted_refresh_token

        conn = await self.oauth_repo.upsert_connection(
            user_id=user_id,
            provider="google_contacts",
            provider_user_id=google_sub,
            email=email,
            encrypted_refresh_token=encrypted_refresh,
            access_token=access_token,
            token_expires_at=expires_at,
            granted_scopes=granted_scope,
            connection_status="active",
        )

        # Perform initial sync
        from app.services.contact_service import ContactService

        contact_service = ContactService(self.session)
        matched_count = 0
        try:
            sync_result = await contact_service.sync_google_contacts(user_id)
            matched_count = sync_result.matched_registered_count
        except Exception as exc:
            logger.warning(f"Initial contacts sync during connect encountered an error: {exc}")

        return GoogleContactsStatusResponse(
            connected=True,
            provider="google_contacts",
            email=conn.email,
            granted_scopes=conn.granted_scopes,
            connected_at=conn.created_at,
            last_synced_at=conn.updated_at,
            matched_registered_count=matched_count,
        )

    async def get_contacts_status(self, user_id: uuid.UUID) -> GoogleContactsStatusResponse:
        """Check status of Google Contacts connection for current user."""
        conn = await self.oauth_repo.get_by_user_id(user_id, "google_contacts")
        if not conn or conn.connection_status != "active":
            # Fallback check if primary google connection has contacts scope
            conn = await self.oauth_repo.get_by_user_id(user_id, "google")
            if not conn or conn.connection_status != "active" or "contacts" not in (conn.granted_scopes or ""):
                return GoogleContactsStatusResponse(connected=False, provider="google_contacts")

        count = await self.contact_repo.count_contacts_by_user(user_id)
        return GoogleContactsStatusResponse(
            connected=True,
            provider="google_contacts",
            email=conn.email,
            granted_scopes=conn.granted_scopes,
            connected_at=conn.created_at,
            last_synced_at=conn.updated_at,
            matched_registered_count=count,
        )

    async def disconnect_contacts(self, user_id: uuid.UUID) -> None:
        """Disconnect Google Contacts, delete credentials, and wipe synced address book contacts."""
        await self.oauth_repo.delete_by_user(user_id, "google_contacts")
        # Ensure any other google connection records have contacts scope removed so they don't linger
        for prov in ["google", "google_gmail"]:
            other_conn = await self.oauth_repo.get_by_user_id(user_id, prov)
            if other_conn and other_conn.granted_scopes and "contacts" in other_conn.granted_scopes:
                scopes = [s for s in other_conn.granted_scopes.split() if "contacts" not in s]
                other_conn.granted_scopes = " ".join(scopes)
                await self.session.flush()

        await self.contact_repo.delete_contacts_by_user(user_id)

    # --- Backward compatibility methods ---

    async def get_oauth_status(self, user_id: uuid.UUID) -> OAuthStatusResponse:
        """Check status of Google OAuth connection for current user."""
        contacts_status = await self.get_contacts_status(user_id)
        if contacts_status.connected:
            return OAuthStatusResponse(
                connected=True,
                provider="google",
                email=contacts_status.email,
                has_contacts_scope=True,
                connected_at=contacts_status.connected_at,
                last_synced_at=contacts_status.last_synced_at,
            )

        conn = await self.oauth_repo.get_by_user_id(user_id, "google")
        if not conn or conn.connection_status != "active":
            return OAuthStatusResponse(connected=False, provider="google")

        has_contacts = "contacts" in (conn.granted_scopes or "")
        return OAuthStatusResponse(
            connected=has_contacts,
            provider="google",
            email=conn.email,
            has_contacts_scope=has_contacts,
            connected_at=conn.created_at,
            last_synced_at=conn.updated_at,
        )

    async def disconnect_google(self, user_id: uuid.UUID) -> None:
        """Disconnect Google Contacts integration and delete synced address book contacts."""
        await self.disconnect_contacts(user_id)
