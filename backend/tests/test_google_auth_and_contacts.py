"""Automated tests for Google OAuth sign-in and Google Contacts synchronization."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import create_oauth_state
from app.models.user import User


@pytest.mark.asyncio
async def test_google_auth_url_endpoint(client: AsyncClient, monkeypatch):
    """Verify generation of Google OAuth authorization URL without silently broadening scopes."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # 1. Default login URL should only request identity scopes (no contacts or gmail)
    response = await client.get("/api/v1/auth/google/url")
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "state" in data
    assert "accounts.google.com" in data["url"]
    assert "test-client-id" in data["url"]
    assert "contacts.readonly" not in data["url"]
    assert "gmail" not in data["url"]
    assert "code_challenge=" in data["url"]


@pytest.mark.asyncio
async def test_google_contacts_connect_url_endpoint(client: AsyncClient, auth_headers: dict[str, str], monkeypatch):
    """Verify dedicated Google Contacts connect URL endpoint requests minimum contacts scope."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    response = await client.get("/api/v1/contacts/google/connect-url", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "contacts.readonly" in data["url"]
    assert "state" in data


@pytest.mark.asyncio
async def test_google_callback_new_user_provisioning(client: AsyncClient, monkeypatch):
    """Verify new user registration via Google OAuth token exchange."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    valid_state = create_oauth_state(purpose="login")
    mock_exchange = AsyncMock(return_value={
        "access_token": "mock-google-access-token",
        "refresh_token": "mock-google-refresh-token",
        "expires_in": 3600,
        "scope": "openid email profile",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "google-sub-123456",
        "email": "sarah.connor@cyberdyne.com",
        "display_name": "Sarah Connor",
        "avatar_url": "https://lh3.googleusercontent.com/avatar/sarah.jpg",
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info):

        response = await client.post("/api/v1/auth/google/callback", json={
            "code": "sample-google-auth-code",
            "state": valid_state,
            "redirect_uri": "http://localhost:5173/auth/google/callback",
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "sarah.connor@cyberdyne.com"
        assert data["user"]["display_name"] == "Sarah Connor"
        assert "sarahconnor" in data["user"]["username"] or "sarah" in data["user"]["username"]


@pytest.mark.asyncio
async def test_google_callback_links_existing_email_user(client: AsyncClient, test_user: User, monkeypatch):
    """Verify linking an existing email-based user account with Google identity."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    mock_exchange = AsyncMock(return_value={
        "access_token": "mock-google-access-token-alice",
        "refresh_token": "mock-google-refresh-token-alice",
        "expires_in": 3600,
        "scope": "openid email profile",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "google-sub-alice-999",
        "email": test_user.email,  # same email: alice@example.com
        "display_name": "Alice Wonderland Updated",
        "avatar_url": "https://lh3.googleusercontent.com/avatar/alice.jpg",
        "email_verified": True,
    })

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info):

        response = await client.post("/api/v1/auth/google/callback", json={
            "code": "sample-google-auth-code-alice",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["id"] == str(test_user.id)
        assert data["user"]["username"] == test_user.username


@pytest.mark.asyncio
async def test_google_contacts_sync_and_matching(
    client: AsyncClient,
    test_user: User,
    test_user_b: User,
    auth_headers: dict[str, str],
    monkeypatch,
):
    """Verify syncing contacts and displaying strictly registered teammates on Alignment Radar."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    # 1. Connect Google Contacts for Alice
    contacts_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "google-token-alice",
        "refresh_token": "google-refresh-alice",
        "expires_in": 3600,
        "scope": "openid email profile https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-alice",
        "email": test_user.email,
        "display_name": test_user.display_name,
        "avatar_url": None,
        "email_verified": True,
    })
    mock_fetch_contacts = AsyncMock(return_value=[
        {
            "contact_email": test_user_b.email,  # bob@example.com (on platform)
            "contact_name": "Bob Builder Colleague",
            "avatar_url": "https://photos.google.com/bob.jpg",
            "google_resource_name": "people/c12345",
        },
        {
            "contact_email": "charlie.external@partner.org",
            "contact_name": "Charlie External",
            "avatar_url": None,
            "google_resource_name": "people/c67890",
        },
    ])

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info), \
         patch("app.services.contact_service.google_provider.fetch_contacts", mock_fetch_contacts):
        connect_res = await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "alice-code",
            "state": contacts_state,
        })
        assert connect_res.status_code == 200
        assert connect_res.json()["connected"] is True
        assert connect_res.json()["matched_registered_count"] == 1

    # 2. Check contacts status endpoint
    status_res = await client.get("/api/v1/contacts/google/status", headers=auth_headers)
    assert status_res.status_code == 200
    assert status_res.json()["connected"] is True
    assert status_res.json()["matched_registered_count"] == 1

    # 3. List contacts: strictly registered teammates are displayed (Charlie is omitted for privacy)
    list_res = await client.get("/api/v1/contacts", headers=auth_headers)
    assert list_res.status_code == 200
    contacts_data = list_res.json()
    assert contacts_data["total"] == 1
    assert len(contacts_data["contacts"]) == 1
    contact = contacts_data["contacts"][0]
    assert contact["contact_email"] == test_user_b.email
    assert contact["is_registered"] is True
    assert contact["registered_username"] == test_user_b.username


@pytest.mark.asyncio
async def test_contacts_privacy_isolation_and_disconnect(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    auth_headers_b: dict[str, str],
    monkeypatch,
):
    """Verify that contacts are strictly private to the user and can be removed upon disconnect."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    contacts_state = create_oauth_state(purpose="contacts", user_id=str(test_user.id))
    mock_exchange = AsyncMock(return_value={
        "access_token": "alice-tok",
        "refresh_token": "alice-ref",
        "expires_in": 3600,
        "scope": "openid email https://www.googleapis.com/auth/contacts.readonly",
    })
    mock_user_info = AsyncMock(return_value={
        "google_sub": "sub-alice-priv",
        "email": test_user.email,
        "display_name": "Alice",
        "avatar_url": None,
        "email_verified": True,
    })
    mock_contacts = AsyncMock(return_value=[
        {"contact_email": "private.client@secret.com", "contact_name": "Private Client"}
    ])

    with patch("app.services.google_auth_service.google_provider.exchange_code", mock_exchange), \
         patch("app.services.google_auth_service.google_provider.get_user_info", mock_user_info), \
         patch("app.services.contact_service.google_provider.fetch_contacts", mock_contacts):
        await client.post("/api/v1/contacts/google/callback", headers=auth_headers, json={
            "code": "code-priv",
            "state": contacts_state,
        })

    # Bob lists contacts: must be 0 (cannot see Alice's contacts)
    bob_list_res = await client.get("/api/v1/contacts", headers=auth_headers_b)
    assert bob_list_res.status_code == 200
    assert bob_list_res.json()["total"] == 0

    # Alice disconnects Google Contacts
    disconnect_res = await client.delete("/api/v1/contacts/google", headers=auth_headers)
    assert disconnect_res.status_code == 200

    # Alice lists contacts: must now be 0
    alice_list_res = await client.get("/api/v1/contacts", headers=auth_headers)
    assert alice_list_res.status_code == 200
    assert alice_list_res.json()["total"] == 0

    # Google Contacts status should be not connected
    status_res = await client.get("/api/v1/contacts/google/status", headers=auth_headers)
    assert status_res.status_code == 200
    assert status_res.json()["connected"] is False
