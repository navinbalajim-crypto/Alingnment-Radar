"""Regression tests verifying Google People API and Gmail API error classification and isolation."""

import uuid
import httpx
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from app.core.config import settings
from app.core.errors import ProviderUnavailableError, RateLimitError, UnauthorizedError
from app.core.security import create_oauth_state
from app.models.user import User
from app.providers.google_provider import google_provider
from app.services.contact_service import ContactService
from app.services.gmail_service import GmailNotificationService
from app.services.google_auth_service import GoogleAuthService


def test_api_disabled_error_extracts_activation_link():
    """Verify that a 403 response with SERVICE_DISABLED extracts the Google Cloud Console activation link."""
    raw_error_payload = {
        "error": {
            "code": 403,
            "message": "Gmail API has not been used in project 558803615890 before or it is disabled.",
            "errors": [{"reason": "accessNotConfigured"}],
            "details": [
                {
                    "reason": "SERVICE_DISABLED",
                    "metadata": {
                        "consumer": "projects/558803615890",
                        "activationUrl": "https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=558803615890",
                    },
                }
            ],
        }
    }
    request = httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages")
    response = httpx.Response(status_code=403, json=raw_error_payload, request=request)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        google_provider._handle_google_api_error(response, "Gmail API")

    err = exc_info.value
    assert "https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=558803615890" in err.message
    assert "disabled in Google Cloud Console" in err.message


def test_insufficient_permissions_error_distinguished():
    """Verify that insufficient scope raises UnauthorizedError instead of claiming API is disabled."""
    raw_error_payload = {
        "error": {
            "code": 403,
            "message": "Request had insufficient authentication scopes.",
            "errors": [{"reason": "insufficientPermissions"}],
        }
    }
    request = httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages")
    response = httpx.Response(status_code=403, json=raw_error_payload, request=request)

    with pytest.raises(UnauthorizedError) as exc_info:
        google_provider._handle_google_api_error(response, "Gmail API")

    assert "permissions were not granted" in exc_info.value.message


def test_rate_limit_error_distinguished():
    """Verify that rate limit quota error raises RateLimitError."""
    raw_error_payload = {
        "error": {
            "code": 403,
            "message": "User Rate Limit Exceeded",
            "errors": [{"reason": "userRateLimitExceeded"}],
        }
    }
    request = httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages")
    response = httpx.Response(status_code=403, json=raw_error_payload, request=request)

    with pytest.raises(RateLimitError) as exc_info:
        google_provider._handle_google_api_error(response, "Gmail API")

    assert "rate limit exceeded" in exc_info.value.message


@pytest.mark.asyncio
async def test_contacts_and_gmail_disconnection_isolation(client: AsyncClient, test_user: User, auth_headers: dict[str, str], monkeypatch):
    """Verify that disconnecting Contacts leaves Gmail intact and vice versa, without lingering scopes."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Connect Contacts
    c_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    c_exchange = AsyncMock(return_value={
        "access_token": "c-tok-test",
        "refresh_token": "c-ref-test",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    user_info = AsyncMock(return_value={
        "google_sub": "sub-test-iso",
        "email": test_user.email,
        "display_name": "Test User",
        "avatar_url": None,
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", c_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", user_info), \
         patch("app.services.google_auth_service.google_provider.fetch_contacts", AsyncMock(return_value=[])):
        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={"code": "c-code", "state": c_state})

    # Connect Gmail
    g_state = create_oauth_state(purpose="gmail", user_id=str(test_user.id))
    g_exchange = AsyncMock(return_value={
        "access_token": "g-tok-test",
        "refresh_token": "g-ref-test",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/gmail.metadata",
    })

    with patch("app.services.gmail_service.google_provider.exchange_code", g_exchange), \
         patch("app.services.gmail_service.google_provider.get_user_info", user_info), \
         patch("app.services.gmail_service.google_provider.fetch_gmail_messages", AsyncMock(return_value={"messages": []})):
        await client.post("/api/v1/gmail/callback", headers=auth_headers, json={"code": "g-code", "state": g_state})

    c_status = (await client.get("/api/v1/contacts/google/status", headers=auth_headers)).json()
    g_status = (await client.get("/api/v1/gmail/status", headers=auth_headers)).json()
    assert c_status["connected"] is True
    assert g_status["connected"] is True

    # Disconnect Contacts only
    del_c = await client.delete("/api/v1/contacts/google", headers=auth_headers)
    assert del_c.status_code == 200

    assert (await client.get("/api/v1/contacts/google/status", headers=auth_headers)).json()["connected"] is False
    assert (await client.get("/api/v1/gmail/status", headers=auth_headers)).json()["connected"] is True

    # Disconnect Gmail only
    del_g = await client.delete("/api/v1/gmail", headers=auth_headers)
    assert del_g.status_code == 200

    assert (await client.get("/api/v1/gmail/status", headers=auth_headers)).json()["connected"] is False


def test_gmail_connect_url_requests_identity_scopes_alongside_metadata_scope():
    """Regression: GmailNotificationService.get_connect_url() must request IDENTITY_SCOPES
    (openid/userinfo.email/userinfo.profile) together with gmail.metadata. The Gmail-connect
    flow immediately calls Google's userinfo endpoint (in connect_gmail_with_code) to resolve
    the connected email address, and that endpoint requires an identity scope on the token.
    Requesting gmail.metadata alone -- the original bug -- produced a token that Google's
    userinfo endpoint rejects, so every Gmail connection failed right after the user granted
    consent. This does not broaden Gmail content access: GMAIL_SCOPES itself still contains
    only gmail.metadata."""
    from urllib.parse import unquote
    from app.core.config import settings as app_settings
    from app.providers.google_provider import GMAIL_SCOPES, IDENTITY_SCOPES
    from app.services.gmail_service import GmailNotificationService

    original_client_id, original_client_secret = app_settings.GOOGLE_CLIENT_ID, app_settings.GOOGLE_CLIENT_SECRET
    app_settings.GOOGLE_CLIENT_ID = "test-client-id"
    app_settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
    try:
        service = GmailNotificationService(session=None)
        resp = service.get_connect_url(user_id=uuid.uuid4())
    finally:
        app_settings.GOOGLE_CLIENT_ID, app_settings.GOOGLE_CLIENT_SECRET = original_client_id, original_client_secret

    decoded_url = unquote(resp.url)
    for scope in IDENTITY_SCOPES:
        assert scope in decoded_url, f"missing identity scope {scope} -- userinfo call will be rejected by Google"
    for scope in GMAIL_SCOPES:
        assert scope in decoded_url
    # Still privacy-scoped: never silently broadened to full Gmail content access.
    assert "gmail.readonly" not in decoded_url
    assert "gmail.modify" not in decoded_url
    assert "mail.google.com" not in decoded_url


@pytest.mark.asyncio
async def test_gmail_scope_mismatch_reproduced_and_resolved(test_user: User):
    """Regression (end-to-end against the real, unmocked google_provider.get_user_info): only
    the network transport is faked, mimicking Google's real behaviour of rejecting
    /oauth2/v3/userinfo calls when the token's granted scope lacks an identity scope.

    (a) Reproduces the original bug: a token granted with gmail.metadata ONLY -- what the
        Gmail-connect flow used to request -- fails the userinfo call with UnauthorizedError.
    (b) Proves the fix: a token granted with IDENTITY_SCOPES + GMAIL_SCOPES together -- what
        GmailNotificationService.get_connect_url now actually requests -- succeeds and
        resolves the connected email address.
    """
    from app.providers.google_provider import GMAIL_SCOPES, IDENTITY_SCOPES

    def fake_userinfo(granted_scope: str) -> httpx.Response:
        has_identity = "openid" in granted_scope and "userinfo.email" in granted_scope
        if has_identity:
            return httpx.Response(
                200,
                json={"sub": "sub-regress-1", "email": test_user.email, "email_verified": True, "name": "Regress User"},
            )
        return httpx.Response(401, json={"error": "invalid_token", "error_description": "insufficient scope"})

    state = {"granted_scope": " ".join(GMAIL_SCOPES)}  # (a) original bug: metadata only

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return fake_userinfo(state["granted_scope"])

    with patch("app.providers.google_provider.httpx.AsyncClient", _FakeAsyncClient):
        with pytest.raises(UnauthorizedError):
            await google_provider.get_user_info("tok-metadata-only")

        # (b) the fix: identity scopes requested alongside gmail.metadata, exactly as
        # GmailNotificationService.get_connect_url does.
        state["granted_scope"] = " ".join(IDENTITY_SCOPES + GMAIL_SCOPES)
        info = await google_provider.get_user_info("tok-with-identity-scopes")
        assert info["email"] == test_user.email
        assert info["google_sub"] == "sub-regress-1"
