"""Mocked-transport tests for the Nebius Token Factory provider and its router integration.

These verify request shape, error mapping, and routing isolation without network access.
They do NOT prove live Nebius inference; that requires a real NEBIUS_API_KEY.
"""

import json
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings, settings
from app.core.errors import ProviderError, ProviderUnavailableError, RateLimitError
from app.providers.nebius_provider import NebiusProvider, nebius_provider
from app.services.ai_router import AIRouter, TaskType

TEST_KEY = "test-nebius-key-123456"
RECOMMENDATION_REPLY = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {"has_intent": True, "category": "music", "query": "tamil film songs", "preferred_providers": ["youtube"]}
                )
            }
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _provider_with(handler) -> NebiusProvider:
    return NebiusProvider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture
def configured_key(monkeypatch):
    monkeypatch.setattr(settings, "NEBIUS_API_KEY", TEST_KEY)
    monkeypatch.setattr(settings, "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
    monkeypatch.setattr(settings, "NEBIUS_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    return TEST_KEY


def test_unconfigured_when_key_is_placeholder(monkeypatch):
    monkeypatch.setattr(settings, "NEBIUS_API_KEY", "xxx")
    assert NebiusProvider().is_configured() is False


def test_configured_when_key_present(configured_key):
    assert NebiusProvider().is_configured() is True


@pytest.mark.asyncio
async def test_unconfigured_provider_raises_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "NEBIUS_API_KEY", "xxx")
    with pytest.raises(ProviderUnavailableError):
        await NebiusProvider().detect_recommendation_intent([{"sender_username": "a", "content": "hi"}])


@pytest.mark.asyncio
async def test_successful_mocked_inference_uses_bearer_auth_and_openai_endpoint(configured_key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=RECOMMENDATION_REPLY)

    provider = _provider_with(handler)
    result = await provider.detect_recommendation_intent([{"sender_username": "a", "content": "play tamil songs"}])

    assert seen["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert seen["auth"] == f"Bearer {TEST_KEY}"
    assert seen["body"]["model"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert result == {
        "has_intent": True,
        "category": "music",
        "query": "tamil film songs",
        "preferred_providers": ["youtube"],
    }


@pytest.mark.asyncio
async def test_thinking_disabled_for_nebius_draft_tasks(configured_key):
    """
    Nebius serves a reasoning model: live testing showed it can spend the entire max_tokens
    budget on chain-of-thought before any answer, leaving content empty (finish_reason=length)
    at the existing 400/600 token limits for suggest_completions/analyze_draft. Disabling
    thinking (verified live, matching NVIDIA NIM's existing behavior) fixes this without
    raising any token limits. This asserts the flag is actually sent for both tasks.
    """
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=RECOMMENDATION_REPLY)

    await _provider_with(handler).suggest_completions("hel", [{"sender_username": "a", "content": "x"}])
    await _provider_with(handler).analyze_draft("hel", [{"sender_username": "a", "content": "x"}])
    assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert bodies[1]["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_truncated_length_response_returns_none_not_false_success(configured_key):
    """A reasoning model that exhausts max_tokens before answering must not be treated as success."""
    truncated_reply = {
        "choices": [{"finish_reason": "length", "message": {"content": "", "reasoning": "thinking forever..."}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 400, "total_tokens": 420},
    }
    provider = _provider_with(lambda r: httpx.Response(200, json=truncated_reply))
    result = await provider.suggest_completions("hel", [{"sender_username": "a", "content": "x"}])
    assert result is None


@pytest.mark.asyncio
async def test_empty_but_complete_response_also_returns_none(configured_key):
    """A clean stop with genuinely empty content is unparseable JSON, not a usable answer."""
    empty_reply = {
        "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 1, "total_tokens": 21},
    }
    provider = _provider_with(lambda r: httpx.Response(200, json=empty_reply))
    result = await provider.suggest_completions("hel", [{"sender_username": "a", "content": "x"}])
    assert result is None


@pytest.mark.asyncio
async def test_authentication_error_is_provider_error_and_does_not_leak_key(configured_key):
    provider = _provider_with(lambda r: httpx.Response(401, json={"error": f"bad key {TEST_KEY}"}))
    with pytest.raises(ProviderError) as info:
        await provider.detect_recommendation_intent([{"sender_username": "a", "content": "x"}])
    assert "401" in str(info.value)
    assert TEST_KEY not in str(info.value)
    assert provider.last_error is not None and TEST_KEY not in provider.last_error


@pytest.mark.asyncio
async def test_rate_limit_maps_to_rate_limit_error_and_trips_breaker(configured_key):
    provider = _provider_with(lambda r: httpx.Response(429, json={}))
    with pytest.raises(RateLimitError):
        await provider.detect_recommendation_intent([{"sender_username": "a", "content": "x"}])
    assert provider.circuit_state == "open"


@pytest.mark.asyncio
async def test_timeout_is_mapped_to_provider_error(configured_key):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        await _provider_with(handler).detect_recommendation_intent([{"sender_username": "a", "content": "x"}])


@pytest.mark.asyncio
async def test_network_failure_is_mapped_to_provider_error(configured_key):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError, match="Network error"):
        await _provider_with(handler).detect_recommendation_intent([{"sender_username": "a", "content": "x"}])


def test_default_adaptive_strategy_never_selects_nebius(monkeypatch):
    monkeypatch.setattr(settings, "AI_ROUTER_STRATEGY", "adaptive")
    router = AIRouter()
    with patch.object(Settings, "is_provider_configured", side_effect=lambda n: n in ("nvidia", "groq", "nebius")):
        provider, _ = router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
    assert provider != "nebius"


def test_forced_nebius_strategy_selects_nebius_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "AI_ROUTER_STRATEGY", "nebius")
    router = AIRouter()
    with patch.object(Settings, "is_provider_configured", side_effect=lambda n: n == "nebius"):
        provider, reason = router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
    assert provider == "nebius"
    assert "nebius" in reason


def test_forced_nebius_without_key_falls_back_to_adaptive_selection(monkeypatch):
    monkeypatch.setattr(settings, "AI_ROUTER_STRATEGY", "nebius")
    router = AIRouter()
    with patch.object(Settings, "is_provider_configured", side_effect=lambda n: n == "nvidia"):
        provider, _ = router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
    assert provider == "nvidia"


@pytest.mark.asyncio
async def test_forced_nebius_failure_does_not_silently_fall_back_to_other_cloud(monkeypatch):
    monkeypatch.setattr(settings, "AI_ROUTER_STRATEGY", "nebius")
    router = AIRouter()

    async def failing(*args, **kwargs):
        raise ProviderError("nebius", "boom")

    with patch.object(Settings, "is_provider_configured", side_effect=lambda n: n in ("nebius", "nvidia", "groq")), \
         patch.object(nebius_provider, "detect_recommendation_intent", side_effect=failing), \
         patch("app.providers.nvidia_provider.nvidia_provider.detect_recommendation_intent") as nv_call:
        result = await router.detect_recommendation_intent([{"sender_username": "a", "content": "x"}])

    assert result is None
    nv_call.assert_not_called()
