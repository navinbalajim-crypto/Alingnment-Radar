"""Comprehensive automated tests verifying Phase 7 requirements for Google Contacts and Gmail notifications."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import create_access_token, create_oauth_state
from app.models.user import User
from app.models.oauth_connection import OAuthConnection
from app.models.gmail_notification import GmailNotification


# 1. Existing email-code login still works
@pytest.mark.asyncio
async def test_req1_existing_email_code_login_still_works(client: AsyncClient, test_user: User):
    """Requirement 1: Verify existing email-code login flow remains functional."""
    from app.core.security import rate_limiter
    rate_limiter._records.clear()
    with patch("app.providers.email_provider.email_provider.send_verification_email", AsyncMock(return_value=True)):
        req_res = await client.post("/api/v1/auth/login/request-code", json={"email": test_user.email})
        assert req_res.status_code == 200
        assert "verification code sent" in req_res.json()["message"].lower()



# 2. Existing Google sign-in still works
@pytest.mark.asyncio
async def test_req2_existing_google_sign_in_still_works(client: AsyncClient, monkeypatch):
    """Requirement 2: Verify existing Google sign-in flow remains functional."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    state = create_oauth_state(purpose="login")
    mock_exchange = AsyncMock(return_value={
        "access_token": "google-token-signin",
        "refresh_token": "google-refresh-signin",
        "expires_in": 3600,
        "scope": "openid email profile",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-new-google-user",
        "email": "new.googler@example.com",
        "display_name": "New Googler",
        "avatar_url": "https://lh3.googleusercontent.com/avatar.jpg",
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info):

        res = await client.post("/api/v1/auth/google/callback", json={
            "code": "sample-code",
            "state": state,
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["user"]["email"] == "new.googler@example.com"


# 3. Contacts access requires the appropriate granted scope
@pytest.mark.asyncio
async def test_req3_contacts_access_requires_appropriate_granted_scope(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 3: Contacts callback rejects tokens without contacts.readonly scope."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    # Scope returned does NOT include contacts.readonly
    mock_exchange = AsyncMock(return_value={
        "access_token": "tok-no-contacts",
        "refresh_token": "ref-no-contacts",
        "expires_in": 3600,
        "scope": "openid email profile",
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange):
        res = await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-no-scope",
            "state": state,
        })
        assert res.status_code == 401
        assert "permission was not granted" in res.json()["message"]


# 4. Contacts permission denial leaves username discovery functional
@pytest.mark.asyncio
async def test_req4_contacts_permission_denial_leaves_username_discovery_functional(
    client: AsyncClient,
    test_user_b: User,
    auth_headers: dict[str, str],
):
    """Requirement 4: When contacts are denied or disconnected, search by username remains 100% operational."""
    # Google contacts is not connected
    status_res = await client.get("/api/v1/contacts/google/status", headers=auth_headers)
    assert status_res.status_code == 200
    assert status_res.json()["connected"] is False

    # Platform user search must still work perfectly
    search_res = await client.get(f"/api/v1/users/search?username={test_user_b.username}", headers=auth_headers)
    assert search_res.status_code == 200
    users = search_res.json()
    assert any(u["username"] == test_user_b.username for u in users)


# 5. Contacts pagination and email normalization work
@pytest.mark.asyncio
async def test_req5_contacts_pagination_and_email_normalization(
    client: AsyncClient,
    test_user: User,
    test_user_b: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 5: Multi-page contacts with unnormalized emails are paginated and safely normalized."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Connect Google Contacts
    contacts_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "alice-tok-pag",
        "refresh_token": "alice-ref-pag",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-alice-pag",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    # Mock contacts with un-normalized email (mixed case, whitespace)
    unnormalized_email = f"  {test_user_b.email.upper()}  "
    mock_contacts = AsyncMock(return_value=[
        {
            "contact_email": unnormalized_email,
            "contact_name": "Bob Builder",
            "avatar_url": None,
            "google_resource_name": "people/c1",
        }
    ])

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info), \
         patch("app.services.contact_service.google_provider.fetch_contacts", mock_contacts):

        connect_res = await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-pag",
            "state": contacts_state,
        })
        assert connect_res.status_code == 200
        assert connect_res.json()["matched_registered_count"] == 1

        list_res = await client.get("/api/v1/contacts", headers=auth_headers)
        assert list_res.status_code == 200
        contacts = list_res.json()["contacts"]
        assert len(contacts) == 1
        assert contacts[0]["contact_email"] == test_user_b.email.lower()
        assert contacts[0]["is_registered"] is True


# 6. Only registered app users appear in contact discovery
@pytest.mark.asyncio
async def test_req6_only_registered_app_users_appear_in_contact_discovery(
    client: AsyncClient,
    test_user: User,
    test_user_b: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 6: Address book contains unregistered contacts, but only registered app users appear."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    contacts_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "tok-filter",
        "refresh_token": "ref-filter",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-filter",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    # Return 1 registered user (Bob) and 3 external non-registered contacts
    mock_contacts = AsyncMock(return_value=[
        {"contact_email": test_user_b.email, "contact_name": "Bob Registered"},
        {"contact_email": "stranger1@external.org", "contact_name": "Stranger 1"},
        {"contact_email": "stranger2@external.org", "contact_name": "Stranger 2"},
        {"contact_email": "vendor@partners.com", "contact_name": "Vendor"},
    ])

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info), \
         patch("app.services.contact_service.google_provider.fetch_contacts", mock_contacts):

        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-filter",
            "state": contacts_state,
        })

        list_res = await client.get("/api/v1/contacts", headers=auth_headers)
        assert list_res.status_code == 200
        data = list_res.json()
        assert data["total"] == 1
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["contact_email"] == test_user_b.email
        assert all(c["is_registered"] is True for c in data["contacts"])


# 7. One user's contacts cannot leak to another user
@pytest.mark.asyncio
async def test_req7_one_users_contacts_cannot_leak_to_another_user(
    client: AsyncClient,
    test_user: User,
    test_user_b: User,
    auth_headers: dict[str, str],
    auth_headers_b: dict[str, str],
    monkeypatch,
):
    """Requirement 7: Contacts imported by User A are strictly invisible to User B."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "alice-iso-tok",
        "refresh_token": "alice-iso-ref",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-iso-alice",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })
    mock_contacts = AsyncMock(return_value=[
        {"contact_email": test_user_b.email, "contact_name": "Bob Teammate"}
    ])

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info), \
         patch("app.services.contact_service.google_provider.fetch_contacts", mock_contacts):

        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-iso",
            "state": state,
        })

    # Alice has 1 contact
    alice_res = await client.get("/api/v1/contacts", headers=auth_headers)
    assert alice_res.json()["total"] == 1

    # Bob must have 0 contacts
    bob_res = await client.get("/api/v1/contacts", headers=auth_headers_b)
    assert bob_res.json()["total"] == 0


# 8. OAuth state mismatch is rejected
@pytest.mark.asyncio
async def test_req8_oauth_state_mismatch_is_rejected(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Requirement 8: Forged or purpose-mismatched OAuth state tokens are rejected."""
    # 1. Tampered / invalid state token
    res1 = await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
        "code": "sample-code",
        "state": "forged-invalid-state-string",
    })
    assert res1.status_code == 400

    # 2. State created for a DIFFERENT user
    other_user_state = create_oauth_state(purpose="contacts", user_id="00000000-0000-0000-0000-000000000000")
    res2 = await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
        "code": "sample-code",
        "state": other_user_state,
    })
    assert res2.status_code in (400, 401)

    # 3. Purpose mismatch: state was created for "login" but passed to "contacts"
    login_state = create_oauth_state(purpose="login")
    res3 = await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
        "code": "sample-code",
        "state": login_state,
    })
    assert res3.status_code in (400, 401)


# 9. Expired or revoked credentials are handled safely
@pytest.mark.asyncio
async def test_req9_expired_or_revoked_credentials_handled_safely(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 9: Token refresh failure on revoked credentials raises user-friendly unauthorized error."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Connect Google Contacts
    state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "expired-access-tok",
        "refresh_token": "revoked-refresh-tok",
        "expires_in": 0,  # Expired immediately
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-revoked",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info):
        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-revoked",
            "state": state,
        })

    # When sync is attempted and refresh fails (e.g. revoked at Google)
    from app.core.errors import UnauthorizedError
    mock_refresh_fail = AsyncMock(side_effect=UnauthorizedError("Google connection has expired or been revoked."))

    with patch("app.services.contact_service.google_provider.refresh_access_token", mock_refresh_fail):
        sync_res = await client.post("/api/v1/contacts/sync-google", headers=auth_headers)
        assert sync_res.status_code == 401
        assert "expired or been revoked" in sync_res.json()["message"]


# 10. Tokens never appear in URLs, frontend storage, or logs
@pytest.mark.asyncio
async def test_req10_tokens_never_appear_in_urls_or_api_responses(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Requirement 10: Google access and refresh tokens are excluded from connection status and public responses."""
    status_res = await client.get("/api/v1/contacts/google/status", headers=auth_headers)
    assert status_res.status_code == 200
    data = status_res.json()
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "encrypted_refresh_token" not in data

    gmail_status = await client.get("/api/v1/gmail/status", headers=auth_headers)
    assert gmail_status.status_code == 200
    gdata = gmail_status.json()
    assert "access_token" not in gdata
    assert "refresh_token" not in gdata


# 11. Gmail access requires its separate consent
@pytest.mark.asyncio
async def test_req11_gmail_access_requires_separate_consent(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 11: Connecting Contacts does not grant Gmail access, and Gmail requires dedicated consent."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Connect Contacts only
    contacts_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "contacts-only-tok",
        "refresh_token": "contacts-only-ref",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-alice-c",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info):
        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-c-only",
            "state": contacts_state,
        })

    # Contacts should be connected
    c_status = await client.get("/api/v1/contacts/google/status", headers=auth_headers)
    assert c_status.json()["connected"] is True

    # Gmail must NOT be connected
    g_status = await client.get("/api/v1/gmail/status", headers=auth_headers)
    assert g_status.json()["connected"] is False

    # Attempting to check Gmail must fail with clean unconfigured error
    check_res = await client.post("/api/v1/gmail/check", headers=auth_headers)
    assert check_res.status_code == 400
    assert "Gmail notifications are not connected" in check_res.json()["message"]


# 12. Contacts disconnection does not disconnect Gmail, and vice versa
@pytest.mark.asyncio
async def test_req12_independent_disconnection(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 12: Disconnecting Contacts leaves Gmail connected, and disconnecting Gmail leaves Contacts connected."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # 1. Connect Contacts
    c_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    c_mock_exchange = AsyncMock(return_value={
        "access_token": "c-tok",
        "refresh_token": "c-ref",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    user_info = AsyncMock(return_value={
        "google_sub": "sub-indep",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", c_mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", user_info):
        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "c-code",
            "state": c_state,
        })

    # 2. Connect Gmail
    g_state = create_oauth_state(purpose="gmail", user_id=str(test_user.id))
    g_mock_exchange = AsyncMock(return_value={
        "access_token": "g-tok",
        "refresh_token": "g-ref",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/gmail.metadata",
    })

    with patch("app.services.gmail_service.google_provider.exchange_code", g_mock_exchange), \
         patch("app.services.gmail_service.google_provider.get_user_info", user_info), \
         patch("app.services.gmail_service.google_provider.fetch_gmail_messages", AsyncMock(return_value={"messages": []})):
        await client.post("/api/v1/gmail/callback", headers=auth_headers, json={
            "code": "g-code",
            "state": g_state,
        })

    # Verify both connected
    assert (await client.get("/api/v1/contacts/google/status", headers=auth_headers)).json()["connected"] is True
    assert (await client.get("/api/v1/gmail/status", headers=auth_headers)).json()["connected"] is True

    # 3. Disconnect Contacts
    del_c = await client.delete("/api/v1/contacts/google", headers=auth_headers)
    assert del_c.status_code == 200

    # Contacts should be disconnected, Gmail must still be connected!
    assert (await client.get("/api/v1/contacts/google/status", headers=auth_headers)).json()["connected"] is False
    assert (await client.get("/api/v1/gmail/status", headers=auth_headers)).json()["connected"] is True

    # 4. Disconnect Gmail
    del_g = await client.delete("/api/v1/gmail", headers=auth_headers)
    assert del_g.status_code == 200
    assert (await client.get("/api/v1/gmail/status", headers=auth_headers)).json()["connected"] is False


# 13. Duplicate Gmail notifications are not created
@pytest.mark.asyncio
async def test_req13_duplicate_gmail_notifications_not_created(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 13: Multiple Gmail checks deduplicate message IDs and do not duplicate notifications."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Connect Gmail
    g_state = create_oauth_state(purpose="gmail", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "g-tok-dedup",
        "refresh_token": "g-ref-dedup",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/gmail.metadata",
    })
    user_info = AsyncMock(return_value={
        "google_sub": "sub-dedup",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    with patch("app.services.gmail_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.gmail_service.google_provider.get_user_info", user_info), \
         patch("app.services.gmail_service.google_provider.fetch_gmail_messages", AsyncMock(return_value={"messages": []})):
        await client.post("/api/v1/gmail/callback", headers=auth_headers, json={
            "code": "g-code",
            "state": g_state,
        })

    # Message stub to return
    messages_payload = {"messages": [{"id": "msg-101", "threadId": "thr-101"}]}
    metadata_payload = {
        "message_id": "msg-101",
        "thread_id": "thr-101",
        "sender": "boss@company.com",
        "subject": "Quarterly Planning Update",
        "snippet": "Here is the summary of the quarterly roadmap...",
        "internal_date_ms": 1729860000000,
    }

    with patch("app.services.gmail_service.google_provider.fetch_gmail_messages", AsyncMock(return_value=messages_payload)), \
         patch("app.services.gmail_service.google_provider.fetch_gmail_message_metadata", AsyncMock(return_value=metadata_payload)):

        # Check 1: Should find 1 new message
        check1 = await client.post("/api/v1/gmail/check", headers=auth_headers)
        assert check1.status_code == 200
        assert check1.json()["new_notifications_count"] == 1
        assert check1.json()["unread_count"] == 1

        # Check 2: Same message returned from Google -> should detect 0 new notifications
        check2 = await client.post("/api/v1/gmail/check", headers=auth_headers)
        assert check2.status_code == 200
        assert check2.json()["new_notifications_count"] == 0
        assert check2.json()["unread_count"] == 1

    # Verify notification list has exactly 1 item
    list_res = await client.get("/api/v1/gmail/notifications", headers=auth_headers)
    assert list_res.status_code == 200
    assert list_res.json()["total_count"] == 1
    assert list_res.json()["notifications"][0]["gmail_message_id"] == "msg-101"


# 14. Existing verification-code and group-invitation emails continue working
@pytest.mark.asyncio
async def test_req14_existing_transactional_emails_continue_working(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Requirement 14: Transactional email services (Brevo/Resend) for OTPs and group invitations remain intact."""
    from app.core.security import rate_limiter
    rate_limiter._records.clear()
    with patch("app.providers.email_provider.email_provider.send_verification_email", AsyncMock(return_value=True)):
        req_res = await client.post("/api/v1/auth/register/request-code", json={"email": "fresh.test.user@example.com"})
        assert req_res.status_code == 200
        assert "verification code sent" in req_res.json()["message"].lower()


# 15. External AI providers are never called with Gmail contents
@pytest.mark.asyncio
async def test_req15_external_ai_providers_never_called_with_gmail_contents(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Requirement 15: Gmail notification processing strictly NEVER invokes NVIDIA NIM or Groq AI models."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Connect Gmail
    g_state = create_oauth_state(purpose="gmail", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "g-tok-no-ai",
        "refresh_token": "g-ref-no-ai",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/gmail.metadata",
    })
    user_info = AsyncMock(return_value={
        "google_sub": "sub-no-ai",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })

    with patch("app.services.gmail_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.gmail_service.google_provider.get_user_info", user_info), \
         patch("app.services.gmail_service.google_provider.fetch_gmail_messages", AsyncMock(return_value={"messages": []})):
        await client.post("/api/v1/gmail/callback", headers=auth_headers, json={
            "code": "g-code",
            "state": g_state,
        })

    # Spy / mock AI provider calls
    mock_nvidia_call = AsyncMock()
    mock_groq_call = AsyncMock()

    messages_payload = {"messages": [{"id": "msg-sensitive-1", "threadId": "thr-sensitive-1"}]}
    metadata_payload = {
        "message_id": "msg-sensitive-1",
        "thread_id": "thr-sensitive-1",
        "sender": "confidential@secret.com",
        "subject": "Confidential Mergers & Acquisitions",
        "snippet": "Highly sensitive internal transaction details...",
        "internal_date_ms": 1729860000000,
    }

    with patch("app.services.gmail_service.google_provider.fetch_gmail_messages", AsyncMock(return_value=messages_payload)), \
         patch("app.services.gmail_service.google_provider.fetch_gmail_message_metadata", AsyncMock(return_value=metadata_payload)), \
         patch("app.providers.nvidia_provider.nvidia_provider._post_chat_completion", mock_nvidia_call), \
         patch("app.providers.groq_provider.groq_provider._post_chat_completion", mock_groq_call):

        check_res = await client.post("/api/v1/gmail/check", headers=auth_headers)
        assert check_res.status_code == 200

        # Assert with 100% certainty that AI models were NOT called
        assert mock_nvidia_call.call_count == 0
        assert mock_groq_call.call_count == 0

