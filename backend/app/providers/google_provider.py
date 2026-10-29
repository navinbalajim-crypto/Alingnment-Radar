"""Google OAuth2 and People API provider for identity verification and contacts sync."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import httpx
from app.core.config import settings
from app.core.errors import BadRequestError, ProviderUnavailableError, RateLimitError, UnauthorizedError
from app.core.logging import logger

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_PEOPLE_CONNECTIONS_URL = "https://people.googleapis.com/v1/people/me/connections"
GOOGLE_GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GOOGLE_MEET_SPACES_URL = "https://meet.googleapis.com/v2/spaces"

IDENTITY_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

CONTACTS_SCOPES = [
    "https://www.googleapis.com/auth/contacts.readonly",
]

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.metadata",
]

MEET_SCOPES = [
    "https://www.googleapis.com/auth/meetings.space.created",
]

DEFAULT_SCOPES = IDENTITY_SCOPES


class GoogleOAuthProvider:
    """Interacts with Google OAuth 2.0, Google People API, and Gmail API."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    @property
    def client_id(self) -> Optional[str]:
        return self._client_id or settings.GOOGLE_CLIENT_ID

    @property
    def client_secret(self) -> Optional[str]:
        return self._client_secret or settings.GOOGLE_CLIENT_SECRET

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri or settings.GOOGLE_REDIRECT_URI

    def is_configured(self) -> bool:
        return (
            bool(self.client_id)
            and self.client_id != "xxx"
            and bool(self.client_secret)
            and self.client_secret != "xxx"
        )

    def validate_configured(self) -> None:
        if not self.is_configured():
            raise ProviderUnavailableError(
                provider="google",
                message="Google OAuth credentials are not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            )

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: Optional[str] = None,
        prompt: str = "consent",
        include_contacts: bool = False,
        scopes: Optional[List[str]] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: str = "S256",
        access_type: str = "offline",
    ) -> str:
        """Build Google OAuth2 authorization URL with PKCE / state protection and scoped access."""
        self.validate_configured()
        if scopes is not None:
            active_scopes = scopes
        elif include_contacts:
            active_scopes = IDENTITY_SCOPES + CONTACTS_SCOPES
        else:
            active_scopes = IDENTITY_SCOPES

        params: Dict[str, Any] = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(active_scopes),
            "access_type": access_type,
            "prompt": prompt,
            "state": state,
            "include_granted_scopes": "true",
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: Optional[str] = None,
        code_verifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens, verifying PKCE if present."""
        self.validate_configured()
        data: Dict[str, Any] = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(GOOGLE_TOKEN_URL, data=data)
            except httpx.RequestError as exc:
                logger.error(f"Network error during Google token exchange: {exc}")
                raise ProviderUnavailableError("google", "Unable to communicate with Google authentication servers.")

        if response.status_code != 200:
            error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            error_desc = error_data.get("error_description") or error_data.get("error") or response.text
            logger.warning(f"Google token exchange failed ({response.status_code}): {error_desc}")
            raise BadRequestError(f"Google authorization failed: {error_desc}")

        return response.json()

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetch authenticated user profile details from Google userinfo endpoint."""
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
            except httpx.RequestError as exc:
                logger.error(f"Network error fetching Google userinfo: {exc}")
                raise ProviderUnavailableError("google", "Unable to reach Google userinfo service.")

        if response.status_code != 200:
            logger.warning(f"Google userinfo request failed ({response.status_code}): {response.text}")
            raise UnauthorizedError("Invalid or expired Google access token.")

        data = response.json()
        return {
            "google_sub": data.get("sub"),
            "email": data.get("email"),
            "display_name": data.get("name") or data.get("given_name"),
            "avatar_url": data.get("picture"),
            "email_verified": data.get("email_verified", False),
        }

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Obtain fresh access token using long-lived OAuth refresh token."""
        self.validate_configured()
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(GOOGLE_TOKEN_URL, data=data)
            except httpx.RequestError as exc:
                logger.error(f"Network error during Google token refresh: {exc}")
                raise ProviderUnavailableError("google", "Unable to refresh Google access credentials.")

        if response.status_code != 200:
            logger.warning(f"Google refresh token rejected: {response.text}")
            raise UnauthorizedError("Google connection has expired or been revoked. Please reconnect your account.")

        return response.json()

    async def fetch_contacts(
        self,
        access_token: str,
        page_size: int = 100,
        max_contacts: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch user's address book contacts via Google People API with full pagination support.
        Extracts primary name, email, photo, and resource name.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        contacts: List[Dict[str, Any]] = []
        seen_emails = set()
        next_page_token: Optional[str] = None

        async with httpx.AsyncClient(timeout=25.0) as client:
            while len(contacts) < max_contacts:
                params: Dict[str, Any] = {
                    "personFields": "names,emailAddresses,photos",
                    "pageSize": min(page_size, 100),
                    "sortOrder": "LAST_MODIFIED_DESCENDING",
                }
                if next_page_token:
                    params["pageToken"] = next_page_token

                try:
                    response = await client.get(GOOGLE_PEOPLE_CONNECTIONS_URL, headers=headers, params=params)
                except httpx.RequestError as exc:
                    logger.error(f"Network error fetching Google People contacts: {exc}")
                    raise ProviderUnavailableError("google", "Failed to retrieve Google Contacts.")

                if response.status_code != 200:
                    self._handle_google_api_error(response, "Google People API")

                data = response.json()
                connections = data.get("connections", [])
                if not connections:
                    break

                for person in connections:
                    emails = person.get("emailAddresses", [])
                    if not emails:
                        continue

                    primary_email_obj = next((e for e in emails if e.get("metadata", {}).get("primary")), emails[0])
                    email_val = primary_email_obj.get("value", "").strip().lower()
                    if not email_val or email_val in seen_emails:
                        continue

                    names = person.get("names", [])
                    primary_name_obj = next((n for n in names if n.get("metadata", {}).get("primary")), names[0] if names else None)
                    display_name = primary_name_obj.get("displayName") if primary_name_obj else None

                    photos = person.get("photos", [])
                    primary_photo = next((p for p in photos if not p.get("default")), photos[0] if photos else None)
                    photo_url = primary_photo.get("url") if primary_photo else None

                    seen_emails.add(email_val)
                    contacts.append({
                        "contact_email": email_val,
                        "contact_name": display_name,
                        "avatar_url": photo_url,
                        "google_resource_name": person.get("resourceName"),
                    })

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break

        return contacts

    def _handle_google_api_error(
        self,
        response: httpx.Response,
        service_name: str,
    ) -> None:
        """
        Distinguishes Google API error conditions:
        - SERVICE_DISABLED / accessNotConfigured (API not enabled in Cloud Console or propagation delay)
        - insufficientPermissions (missing OAuth scope / user consent)
        - rateLimitExceeded / userRateLimitExceeded (Google quota / rate limit)
        - 401 Unauthorized (invalid / expired token)
        - Other provider errors
        """
        status_code = response.status_code
        try:
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        except Exception:
            data = {}

        error_obj = data.get("error", {}) if isinstance(data, dict) else {}
        error_msg = error_obj.get("message") if isinstance(error_obj, dict) else str(data)
        errors_list = error_obj.get("errors", []) if isinstance(error_obj, dict) else []
        details_list = error_obj.get("details", []) if isinstance(error_obj, dict) else []

        reasons = set()
        activation_url = None
        project_id = None

        for err in errors_list:
            if isinstance(err, dict) and err.get("reason"):
                reasons.add(err["reason"])

        for detail in details_list:
            if isinstance(detail, dict):
                if detail.get("reason"):
                    reasons.add(detail["reason"])
                meta = detail.get("metadata", {})
                if meta.get("activationUrl"):
                    activation_url = meta.get("activationUrl")
                if meta.get("consumer"):
                    project_id = meta.get("consumer").replace("projects/", "")

        if status_code == 401:
            logger.warning(f"Google {service_name} 401 Unauthorized: {error_msg}")
            raise UnauthorizedError(f"Google {service_name} access token has expired or is invalid. Please reconnect.")

        if status_code == 403:
            logger.warning(f"Google {service_name} 403 Forbidden (reasons={reasons}): {error_msg}")
            if "SERVICE_DISABLED" in reasons or "accessNotConfigured" in reasons or (error_msg and "disabled" in error_msg.lower()):
                if "gmail" in service_name.lower():
                    api_slug = "gmail"
                elif "meet" in service_name.lower():
                    api_slug = "meet"
                else:
                    api_slug = "people"
                act_link = activation_url or (
                    f"https://console.developers.google.com/apis/api/{api_slug}.googleapis.com/overview"
                    + (f"?project={project_id}" if project_id else "")
                )
                raise ProviderUnavailableError(
                    provider="google",
                    message=(
                        f"{service_name} is disabled in Google Cloud Console. "
                        f"Enable it at: {act_link} then retry. "
                        f"If you recently enabled it, wait a few minutes for Google propagation."
                    ),
                )
            if "insufficientPermissions" in reasons or "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons:
                raise UnauthorizedError(
                    f"Google {service_name} permissions were not granted. Please reconnect and grant the required scope on the consent screen."
                )
            if "rateLimitExceeded" in reasons or "userRateLimitExceeded" in reasons:
                raise RateLimitError(f"Google {service_name} quota or rate limit exceeded. Please try again later.")

            raise UnauthorizedError(f"Google {service_name} permission error: {error_msg or 'Access forbidden'}")

        if status_code >= 500:
            raise ProviderUnavailableError("google", f"Google {service_name} service is currently unavailable ({status_code}).")

        raise ProviderUnavailableError("google", f"Google {service_name} returned error ({status_code}): {error_msg or response.text}")

    async def fetch_gmail_messages(
        self,
        access_token: str,
        max_results: int = 10,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch message identifiers from Gmail API using metadata scope.
        Returns list of message stubs {'id': str, 'threadId': str}.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        params: Dict[str, Any] = {"maxResults": min(max_results, 50)}
        if page_token:
            params["pageToken"] = page_token
        if query:
            params["q"] = query

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.get(GOOGLE_GMAIL_MESSAGES_URL, headers=headers, params=params)
            except httpx.RequestError as exc:
                logger.error(f"Network error fetching Gmail messages: {exc}")
                raise ProviderUnavailableError("google", "Failed to retrieve Gmail messages.")

        if response.status_code != 200:
            self._handle_google_api_error(response, "Gmail API")

        return response.json()

    async def fetch_gmail_message_metadata(
        self,
        access_token: str,
        message_id: str,
    ) -> Dict[str, Any]:
        """
        Retrieve minimal email metadata (Subject, From, Date, snippet) for a single message.
        Does NOT fetch email bodies or attachments.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{GOOGLE_GMAIL_MESSAGES_URL}/{message_id}"
        params = [
            ("format", "metadata"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "Date"),
        ]

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
            except httpx.RequestError as exc:
                logger.error(f"Network error fetching Gmail message metadata for {message_id}: {exc}")
                raise ProviderUnavailableError("google", "Failed to retrieve Gmail message metadata.")

        if response.status_code != 200:
            self._handle_google_api_error(response, "Gmail API")

        data = response.json()
        headers_list = data.get("payload", {}).get("headers", [])
        headers_map = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

        sender = headers_map.get("from")
        subject = headers_map.get("subject") or "(No Subject)"
        date_str = headers_map.get("date")
        snippet = data.get("snippet", "")

        return {
            "message_id": data.get("id"),
            "thread_id": data.get("threadId"),
            "sender": sender,
            "subject": subject,
            "snippet": snippet[:400] if snippet else None,
            "date_str": date_str,
            "internal_date_ms": int(data.get("internalDate", 0)) if data.get("internalDate") else None,
        }

    async def create_meeting_space(
        self,
        access_token: str,
        space_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a Google Meet space using the official Google Meet REST API v2.
        https://developers.google.com/meet/api/guides/overview
        Endpoint: POST https://meet.googleapis.com/v2/spaces
        Scope: https://www.googleapis.com/auth/meetings.space.created
        """
        self.validate_configured()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = space_config or {}

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.post(GOOGLE_MEET_SPACES_URL, headers=headers, json=body)
            except httpx.RequestError as exc:
                logger.error(f"Network error calling Google Meet API: {exc}")
                raise ProviderUnavailableError("google", "Unable to connect to Google Meet service.")

        if response.status_code not in (200, 201):
            self._handle_google_api_error(response, "Google Meet API")

        data = response.json()
        meeting_uri = data.get("meetingUri")
        if not meeting_uri:
            logger.error(f"Google Meet API returned unexpected payload missing meetingUri: {data}")
            raise BadRequestError("Google Meet API did not return a valid meeting URI.")

        return {
            "meeting_uri": meeting_uri,
            "meeting_code": data.get("meetingCode"),
            "space_name": data.get("name"),
            "config": data.get("config", {}),
        }


google_provider = GoogleOAuthProvider()

