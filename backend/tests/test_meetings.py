"""Tests for Google Meet space creation, OAuth scope enforcement, and meeting invitations."""

import uuid
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.meeting_invitation import MeetingInvitation
from app.models.message import Message
from app.models.oauth_connection import OAuthConnection
from app.models.user import User
from app.providers.google_provider import google_provider
from app.services.conversation_service import ConversationService


@pytest.fixture
async def direct_conversation(db_session: AsyncSession, test_user: User, test_user_b: User) -> Conversation:
    conv_service = ConversationService(db_session)
    summary = await conv_service.get_or_create_direct_conversation(test_user.id, test_user_b.username)
    await db_session.commit()
    conv = await conv_service.conv_repo.get_by_id(summary.id)
    assert conv is not None
    return conv


@pytest.mark.asyncio
async def test_meeting_creation_requires_auth_when_scope_missing(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
):
    """When Google OAuth scope for Meet is not granted, return requires_auth and auth URL."""
    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/meet",
        json={"client_token": "token_1"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["requires_auth"] is True
    assert "authorization_url" in data
    assert "https://accounts.google.com/o/oauth2/v2/auth" in data["authorization_url"]
    assert "meetings.space.created" in data["authorization_url"]
    assert data["invitation"] is None


@pytest.mark.asyncio
async def test_meeting_creation_authorized_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    direct_conversation: Conversation,
    auth_headers: dict,
):
    """When user has granted Google Meet scope, call Google Meet REST API and persist meeting space."""
    from datetime import datetime, timezone, timedelta
    oauth_conn = OAuthConnection(
        user_id=test_user.id,
        provider="google",
        provider_user_id="google-sub-123",
        email=test_user.email,
        access_token="mock_valid_access_token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        granted_scopes="openid email https://www.googleapis.com/auth/meetings.space.created",
        connection_status="active",
    )
    db_session.add(oauth_conn)
    await db_session.commit()

    mock_meet_response = {
        "meetingUri": "https://meet.google.com/abc-defg-hij",
        "meetingCode": "abc-defg-hij",
        "name": "spaces/xyz123",
    }

    with patch.object(google_provider, "create_meeting_space", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_meet_response

        res = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/meet",
            json={"client_token": "token_call_abc"},
            headers=auth_headers,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["requires_auth"] is False
        assert data["invitation"] is not None
        assert data["invitation"]["meeting_uri"] == "https://meet.google.com/abc-defg-hij"
        assert data["invitation"]["meeting_code"] == "abc-defg-hij"
        assert data["invitation"]["space_name"] == "spaces/xyz123"
        assert data["message"] is not None
        assert data["message"]["message_type"] == "meeting_invitation"

    # Verify meeting invitation in database
    inv_stmt = select(MeetingInvitation).where(MeetingInvitation.conversation_id == direct_conversation.id)
    inv = (await db_session.execute(inv_stmt)).scalar_one_or_none()
    assert inv is not None
    assert inv.meeting_uri == "https://meet.google.com/abc-defg-hij"
    assert inv.creator_id == test_user.id


@pytest.mark.asyncio
async def test_meeting_creation_idempotency_deduplication(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    direct_conversation: Conversation,
    auth_headers: dict,
):
    """Subsequent requests with identical client_token reuse the existing meeting space."""
    from datetime import datetime, timezone, timedelta
    oauth_conn = OAuthConnection(
        user_id=test_user.id,
        provider="google",
        provider_user_id="google-sub-123",
        email=test_user.email,
        access_token="mock_valid_access_token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        granted_scopes="https://www.googleapis.com/auth/meetings.space.created",
        connection_status="active",
    )
    db_session.add(oauth_conn)
    await db_session.commit()

    mock_meet_response = {
        "meetingUri": "https://meet.google.com/dedup-123-abc",
        "meetingCode": "dedup-123-abc",
        "name": "spaces/dedup_space",
    }

    with patch.object(google_provider, "create_meeting_space", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_meet_response

        # First request
        res1 = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/meet",
            json={"client_token": "call_dedup_key_999"},
            headers=auth_headers,
        )
        assert res1.status_code == 200

        # Second request with same client_token
        res2 = await client.post(
            f"/api/v1/conversations/{direct_conversation.id}/meet",
            json={"client_token": "call_dedup_key_999"},
            headers=auth_headers,
        )
        assert res2.status_code == 200
        assert res2.json()["invitation"]["meeting_uri"] == "https://meet.google.com/dedup-123-abc"
        # Only called provider once
        assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_meeting_creation_unauthorized_user(
    client: AsyncClient,
    direct_conversation: Conversation,
    db_session: AsyncSession,
):
    """A non-member cannot create or access meeting invitations for a conversation."""
    charlie = User(
        email="charlie@example.com",
        username="charlie",
        username_normalized="charlie",
        display_name="Charlie Stranger",
        is_active=True,
    )
    db_session.add(charlie)
    await db_session.commit()
    from app.core.security import create_access_token
    charlie_token = create_access_token(user_id=str(charlie.id), username=charlie.username)

    res = await client.post(
        f"/api/v1/conversations/{direct_conversation.id}/meet",
        json={"client_token": "charlie_token"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_meeting_auth_url_endpoint(
    client: AsyncClient,
    direct_conversation: Conversation,
    auth_headers: dict,
):
    """GET /conversations/{id}/meet/auth-url returns Google OAuth URL with Meet scope."""
    res = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/meet/auth-url",
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "authorization_url" in data
    assert "meetings.space.created" in data["authorization_url"]


@pytest.mark.asyncio
async def test_meeting_creation_group_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_user_b: User,
    auth_headers: dict,
):
    """Meeting creation works seamlessly in group conversations."""
    from app.repositories.conversation_repo import ConversationRepository
    from datetime import datetime, timezone, timedelta
    conv_repo = ConversationRepository(db_session)
    group_conv = await conv_repo.create_group_conversation(
        title="Engineering Sync",
        creator_id=test_user.id,
        initial_member_ids=[test_user_b.id],
    )
    await db_session.commit()
    group_id = group_conv.id

    oauth_conn = OAuthConnection(
        user_id=test_user.id,
        provider="google",
        provider_user_id="google-sub-group",
        email=test_user.email,
        access_token="valid_group_token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        granted_scopes="https://www.googleapis.com/auth/meetings.space.created",
        connection_status="active",
    )
    db_session.add(oauth_conn)
    await db_session.commit()

    with patch.object(
        google_provider,
        "create_meeting_space",
        new_callable=AsyncMock,
        return_value={"meetingUri": "https://meet.google.com/grp-sync-123", "name": "spaces/grp123"},
    ):
        res = await client.post(
            f"/api/v1/conversations/{group_id}/meet",
            json={"client_token": "token_group_call"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["invitation"]["meeting_uri"] == "https://meet.google.com/grp-sync-123"


@pytest.mark.asyncio
async def test_meet_oauth_callback_with_json_body(
    client: AsyncClient,
    auth_headers: dict,
):
    """Callback accepts OAuth code and state in JSON payload (from frontend service)."""
    with patch("app.api.v1.meetings.GoogleMeetService.connect_google_meet", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = {"status": "connected", "scope": "openid email https://www.googleapis.com/auth/meetings.space.created"}

        res = await client.post(
            "/api/v1/auth/google/meet/callback",
            json={"code": "auth_code_from_json", "state": "test_state_123"},
            headers=auth_headers,
        )

        assert res.status_code == 200
        assert res.json()["status"] == "connected"
        mock_connect.assert_called_once()
        assert mock_connect.call_args.kwargs["code"] == "auth_code_from_json"
        assert mock_connect.call_args.kwargs["state"] == "test_state_123"


@pytest.mark.asyncio
async def test_meet_oauth_callback_with_query_params(
    client: AsyncClient,
    auth_headers: dict,
):
    """Callback also accepts OAuth code in query params when redirected directly."""
    with patch("app.api.v1.meetings.GoogleMeetService.connect_google_meet", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = {"status": "connected", "scope": "meet_scope"}

        res = await client.post(
            "/api/v1/auth/google/meet/callback?code=auth_code_from_query&state=query_state",
            headers=auth_headers,
        )

        assert res.status_code == 200
        assert res.json()["status"] == "connected"
        assert mock_connect.call_args.kwargs["code"] == "auth_code_from_query"


@pytest.mark.asyncio
async def test_meet_oauth_callback_missing_code_raises_422(
    client: AsyncClient,
    auth_headers: dict,
):
    """Callback returns 422 Unprocessable Entity when code is missing in both body and query params."""
    res = await client.post(
        "/api/v1/auth/google/meet/callback",
        json={"state": "missing_code_state"},
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert "Authorization code is required" in res.json()["detail"]



@pytest.mark.asyncio
async def test_meet_connect_requires_state_bound_to_the_current_user(
    db_session: AsyncSession,
    test_user: User,
    test_user_b: User,
):
    """The Meet OAuth code is only exchanged with a signed state issued to the same user (as Gmail/Contacts)."""
    from app.core.errors import BadRequestError, UnauthorizedError
    from app.core.security import create_oauth_state
    from app.services.google_meet_service import GoogleMeetService

    service = GoogleMeetService(db_session)
    with patch.object(google_provider, "exchange_code", new_callable=AsyncMock) as mock_exchange:
        with pytest.raises(BadRequestError):
            await service.connect_google_meet(code="c", state=None, user_id=test_user.id)
        bob_state = create_oauth_state(purpose="connect_meet", user_id=str(test_user_b.id))
        with pytest.raises(UnauthorizedError):
            await service.connect_google_meet(code="c", state=bob_state, user_id=test_user.id)
        assert mock_exchange.call_count == 0


@pytest.mark.asyncio
async def test_disabled_meet_api_error_links_to_the_meet_api_console_page_not_people_api():
    """Regression: when the Google Meet API itself is disabled in the Cloud Console, the
    activation link Google's error message generates must point at the Meet API's own
    console page. It previously always fell back to the People API page for any service
    that wasn't Gmail, which is the wrong page for every other integration (Meet included)
    and would send the user to fix the wrong setting."""
    import httpx
    from app.core.errors import ProviderUnavailableError

    error_payload = {
        "error": {
            "code": 403,
            "message": "Google Meet API has not been used in project 123456 before or it is disabled.",
            "errors": [{"reason": "SERVICE_DISABLED"}],
        }
    }
    response = httpx.Response(
        status_code=403,
        json=error_payload,
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://meet.googleapis.com/v2/spaces"),
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        google_provider._handle_google_api_error(response, "Google Meet API")

    assert "meet.googleapis.com" in str(exc_info.value)
    assert "people.googleapis.com" not in str(exc_info.value)
