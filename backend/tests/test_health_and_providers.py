"""Automated tests for health checks, operations monitoring, and provider error handling."""

from unittest.mock import AsyncMock, patch
import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings, settings
from app.core.errors import ProviderError, ProviderUnavailableError
from app.models.conversation import Conversation, ConversationMember
from app.models.user import User
from app.providers.spotify_provider import SpotifyProvider
from app.providers.tavily_provider import TavilyProvider
from app.providers.youtube_provider import YouTubeProvider


@pytest.mark.asyncio
async def test_health_and_readiness_endpoints(client: AsyncClient):
    # 1. Health liveness
    h_resp = await client.get("/health")
    assert h_resp.status_code == 200
    assert h_resp.json()["status"] == "ok"
    assert h_resp.json()["app_name"] == settings.APP_NAME

    # 2. Readiness probe
    with patch("app.api.v1.health.check_database_connection", new_callable=AsyncMock) as mock_db_check:
        mock_db_check.return_value = True
        r_resp = await client.get("/ready")
        assert r_resp.status_code == 200
        r_data = r_resp.json()
        assert r_data["status"] == "ready"
        assert r_data["database_connected"] is True


@pytest.mark.asyncio
async def test_ai_items_endpoint(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    # Setup conversation
    conv = Conversation(is_group=True, title="Project Sync", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))
    await db_session.commit()

    resp = await client.get(f"/api/v1/conversations/{conv.id}/ai-items", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "findings" in data
    assert "recommendations" in data


@pytest.mark.asyncio
async def test_unconfigured_providers_raise_clear_errors():
    test_settings = Settings(
        NVIDIA_API_KEY="xxx",
        YOUTUBE_DATA_API_KEY="xxx",
        SPOTIFY_CLIENT_ID="xxx",
        TAVILY_API_KEY="xxx",
        BREVO_API_KEY="xxx",
        BREVO_FROM_EMAIL="xxx",
        RESEND_API_KEY="xxx",
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        test_settings.validate_provider_availability("nvidia")
    assert "NVIDIA NIM" in str(exc_info.value) or "nvidia" in str(exc_info.value)

    with pytest.raises(ProviderUnavailableError):
        test_settings.validate_provider_availability("youtube")

    with pytest.raises(ProviderUnavailableError):
        test_settings.validate_provider_availability("brevo")


@pytest.mark.asyncio
async def test_provider_network_and_timeout_errors():
    # YouTube timeout handling
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    yt = YouTubeProvider(client=mock_client)
    with patch.object(Settings, "is_provider_configured", return_value=True):
        with pytest.raises(ProviderError) as exc:
            await yt.search_videos("tamil songs")
        assert "timed out" in str(exc.value)

    # Tavily error handling
    mock_tavily_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock()
    mock_response.status_code = 502
    mock_tavily_client.post.return_value = mock_response

    tv = TavilyProvider(client=mock_tavily_client)
    with patch.object(Settings, "is_provider_configured", return_value=True):
        with pytest.raises(ProviderError) as exc_tv:
            await tv.search("cricket live score")
        assert "Search failed with status 502" in str(exc_tv.value)


def test_production_refuses_placeholder_or_short_signing_secrets():
    """APP_ENV=production must not start with the example secrets (tokens could be forged)."""
    from pydantic import ValidationError

    strong = "s" * 40
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="replace_with_a_long_random_secret", OTP_HMAC_SECRET=strong)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY=strong, OTP_HMAC_SECRET="short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY=strong, OTP_HMAC_SECRET=strong, FRONTEND_ORIGINS=["*"])
    ok = Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY=strong, OTP_HMAC_SECRET=strong,
                  FRONTEND_ORIGINS=["https://app.example.com"])
    assert ok.is_production
    # development keeps working with the example values
    assert not Settings(_env_file=None, APP_ENV="development").is_production
