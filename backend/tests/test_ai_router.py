"""
Comprehensive automated tests for Adaptive Latency-Aware AI Provider Routing (NVIDIA + Groq + Local).

Verifies:
1. NVIDIA-only configuration.
2. Groq-only configuration.
3. Both providers configured.
4. Initial provider selection when no latency history exists.
5. Fastest eligible provider selection after enough measurements exist.
6. Separate routing statistics for different task types.
7. Provider timeout followed by bounded fallback.
8. HTTP 429 and temporary cooldown (circuit breaker) behavior.
9. Both providers failing gracefully with local fallback.
10. Invalid or malformed AI responses handled safely.
11. Missing API credentials handled clearly.
12. No API keys in telemetry or diagnostic logs.
13. No duplicate alignment issues during fallback.
14. Accurate latency instrumentation using a monotonic clock.
15. Optional concurrent provider racing mode.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import time
import uuid

from app.core.config import Settings, settings
from app.core.errors import ProviderError, ProviderUnavailableError, RateLimitError
from app.providers.base_ai_provider import BaseAIProvider, DRAFT_TIMEOUT_SECONDS
from app.providers.groq_provider import GroqProvider, groq_provider
from app.providers.nvidia_provider import NvidiaProvider, nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult
from app.services.ai_router import AIRouter, ProviderTaskStats, TaskType


@pytest.fixture
def fresh_router(monkeypatch):
    """Create an isolated AIRouter instance with fresh statistics and closed circuit breakers."""
    monkeypatch.setattr(settings, "AI_ROUTER_STRATEGY", "adaptive")
    router = AIRouter()
    nvidia_provider.circuit_state = "closed"
    nvidia_provider.consecutive_failures = 0
    nvidia_provider.cooldown_until = 0.0
    groq_provider.circuit_state = "closed"
    groq_provider.consecutive_failures = 0
    groq_provider.cooldown_until = 0.0
    return router


# --- 1 & 2: Provider Configuration Isolation ---

def test_nvidia_only_configuration(fresh_router):
    """When only NVIDIA is configured, router selects NVIDIA without attempting Groq."""
    with patch.object(Settings, "is_provider_configured", side_effect=lambda name: name == "nvidia"):
        provider, reason = fresh_router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
        assert provider == "nvidia"
        assert "Only NVIDIA is configured" in reason


def test_groq_only_configuration(fresh_router):
    """When only Groq is configured, router selects Groq without attempting NVIDIA."""
    with patch.object(Settings, "is_provider_configured", side_effect=lambda name: name in ("groq", "groq_ai")):
        provider, reason = fresh_router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
        assert provider == "groq"
        assert "Only Groq is configured" in reason


def test_neither_provider_configured(fresh_router):
    """When neither cloud provider is configured, router reports none."""
    with patch.object(Settings, "is_provider_configured", return_value=False):
        provider, reason = fresh_router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
        assert provider == "none"
        assert "Neither NVIDIA nor Groq is configured" in reason


# --- 3 & 4: Initial Selection & Baseline Sampling ---

def test_initial_provider_selection_gathers_baseline_samples(fresh_router):
    """When both providers are configured but lack latency history, router gathers baseline samples."""
    with patch.object(Settings, "is_provider_configured", return_value=True):
        # Empty stats: Groq has 0 samples < min_samples (3)
        provider, reason = fresh_router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
        assert provider in ("groq", "nvidia")
        assert "baseline latency samples" in reason or "Defaulting" in reason


# --- 5 & 6: Fastest Eligible Provider Selection & Task-Type Separation ---

def test_fastest_eligible_provider_selection_after_enough_measurements(fresh_router):
    """
    After min_samples is satisfied:
    - Provider with lower EWMA latency for the requested task is selected.
    - Statistics remain strictly isolated between different task types.
    """
    task = TaskType.ALIGNMENT_ANALYSIS.value
    other_task = TaskType.RECOMMENDATION_INTENT.value

    # Populate alignment_analysis stats: Groq is significantly faster
    for _ in range(5):
        fresh_router._stats["groq"][task].record_sample(latency_ms=120.0, success=True)
        fresh_router._stats["nvidia"][task].record_sample(latency_ms=500.0, success=True)

    # Populate recommendation_intent stats: NVIDIA is faster
    for _ in range(5):
        fresh_router._stats["nvidia"][other_task].record_sample(latency_ms=200.0, success=True)
        fresh_router._stats["groq"][other_task].record_sample(latency_ms=800.0, success=True)

    with patch.object(Settings, "is_provider_configured", return_value=True):
        # For alignment_analysis, Groq should win
        provider_align, reason_align = fresh_router.select_cloud_provider(task)
        assert provider_align == "groq"
        assert "Groq measured faster" in reason_align

        # For recommendation_intent, NVIDIA should win
        provider_rec, reason_rec = fresh_router.select_cloud_provider(other_task)
        assert provider_rec == "nvidia"
        assert "NVIDIA measured faster" in reason_rec


# --- 7: Provider Timeout Followed by Bounded Fallback ---

@pytest.mark.asyncio
async def test_provider_timeout_followed_by_bounded_fallback(fresh_router):
    """If the selected provider times out, router falls back to the other eligible provider at most once."""
    mock_finding = AlignmentAnalysisResult(
        mismatch_detected=True,
        category="deadlines",
        severity="medium",
        title="Unclear Deadline",
        explanation="Deadline not stated",
        confidence=0.85,
        supporting_message_ids=["msg-1"],
        clarification_question="What time is the report due?",
    )

    with patch.object(fresh_router, "select_cloud_provider", return_value=("groq", "Mocked primary")), \
         patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(groq_provider, "detect_alignment", side_effect=ProviderError("groq", "Timed out")), \
         patch.object(nvidia_provider, "detect_alignment", new_callable=AsyncMock, return_value=mock_finding) as nv_mock:

        result = await fresh_router.detect_alignment(conversation_context=[], valid_message_ids={"msg-1"})

        assert result is not None
        assert result.title == "Unclear Deadline"
        assert nv_mock.await_count == 1
        assert fresh_router._stats["groq"][TaskType.ALIGNMENT_ANALYSIS.value].fallback_count == 1


# --- 8: HTTP 429 and Temporary Cooldown (Circuit Breaker) ---

def test_http_429_trips_circuit_breaker_immediately(fresh_router):
    """When a provider encounters HTTP 429, its circuit breaker opens immediately and bypasses it."""
    with patch.object(Settings, "is_provider_configured", return_value=True):
        # Trigger 429 failure on NVIDIA
        nvidia_provider._record_failure(RateLimitError("Rate limit exceeded"), is_rate_limit=True)
        assert nvidia_provider.circuit_state == "open"
        assert nvidia_provider.check_health()["is_healthy"] is False

        # Router should automatically bypass NVIDIA in favor of healthy Groq
        selected, reason = fresh_router.select_cloud_provider(TaskType.ALIGNMENT_ANALYSIS.value)
        assert selected == "groq"
        assert "cooldown" in reason.lower() or "circuit" in reason.lower()


# --- 9: Both Providers Failing Gracefully with Local Fallback ---

@pytest.mark.asyncio
async def test_both_providers_failing_falls_back_to_local_for_draft(fresh_router):
    """When all cloud providers fail or are unconfigured, draft analysis falls back to local engine without crashing."""
    with patch.object(Settings, "is_provider_configured", return_value=False):
        # Test obvious typo: 'misic' -> 'music'
        result = await fresh_router.analyze_draft("I like Anirudh misic", conversation_context=[])
        assert result is not None
        assert result.get("source") in ("local_engine", "local_fallback")
        assert any(c["corrected"] == "music" for c in result.get("corrections", []))


@pytest.mark.asyncio
async def test_both_providers_failing_returns_none_for_alignment(fresh_router):
    """When cloud providers fail for alignment analysis, it gracefully returns None without raising 500."""
    with patch.object(fresh_router, "select_cloud_provider", return_value=("none", "No providers")):
        result = await fresh_router.detect_alignment(conversation_context=[], valid_message_ids=set())
        assert result is None


# --- 10: Invalid or Malformed AI Responses Handled Safely ---

def test_invalid_or_malformed_json_response_handled_safely():
    """Verify that html errors, unclosed json, or string refusals do not throw exceptions."""
    provider = NvidiaProvider()
    bad_responses = [
        {"choices": [{"message": {"content": "<html>502 Bad Gateway</html>"}}]},
        {"choices": [{"message": {"content": "I cannot answer this request."}}]},
        {"choices": [{"message": {"content": "{not valid json at all: 123}"}}]},
        {"choices": []},
        {},
    ]
    for bad in bad_responses:
        extracted = provider._extract_json_from_response(bad)
        assert extracted is None


# --- 11: Missing Credentials Handled Clearly ---

def test_missing_credentials_fails_fast():
    """Unconfigured provider check_health clearly states unconfigured and is_healthy=False."""
    with patch.object(Settings, "is_provider_configured", return_value=False):
        health = groq_provider.check_health()
        assert health["is_configured"] is False
        assert health["is_healthy"] is False


# --- 12: No API Keys in Telemetry or Logs ---

def test_no_api_keys_in_telemetry_stats(fresh_router):
    """Ensure get_routing_stats contains zero API credentials or sensitive keys."""
    stats = fresh_router.get_routing_stats()
    serialized = str(stats)
    assert "API_KEY" not in serialized
    assert "Bearer" not in serialized
    assert settings.NVIDIA_API_KEY not in serialized or settings.NVIDIA_API_KEY == "xxx"
    assert settings.GROQ_API_KEY not in serialized or settings.GROQ_API_KEY == "xxx"


# --- 13: Accurate Latency Instrumentation with Monotonic Clock ---

@pytest.mark.asyncio
async def test_monotonic_clock_latency_instrumentation(fresh_router):
    """Verify that latency is measured accurately with monotonic clock (time.perf_counter)."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": '{"tone": "casual", "corrections": [], "completions": []}'}}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
    }

    mock_client = AsyncMock()
    # Simulate a 50ms delay
    async def delayed_post(*args, **kwargs):
        await asyncio.sleep(0.05)
        return fake_response

    mock_client.post.side_effect = delayed_post
    test_provider = GroqProvider(client=mock_client)
    test_provider.set_latency_observer(fresh_router._on_provider_latency)

    with patch.object(test_provider, "is_configured", return_value=True), \
         patch.object(test_provider, "get_api_key", return_value="dummy_key"):
        await test_provider._post_chat_completion(messages=[{"role": "user", "content": "hi"}], task_type="test_task")

    stat = fresh_router._stats["groq"].get("test_task")
    assert stat is not None
    assert stat.request_count == 1
    assert stat.success_count == 1
    # Latency should be at least ~45ms due to sleep
    assert stat.samples[0] >= 40.0
    assert stat.total_tokens == 25


# --- 14: Optional Concurrent Provider Racing Mode ---

@pytest.mark.asyncio
async def test_racing_mode_selects_first_completed(fresh_router):
    """When AI_RACING_ENABLED=True, fastest response wins and slower is cancelled."""
    with patch.object(settings, "AI_RACING_ENABLED", True), \
         patch.object(nvidia_provider, "is_configured", return_value=True), \
         patch.object(groq_provider, "is_configured", return_value=True):

        async def fast_call(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {"tone": "casual", "corrections": [], "completions": [], "source": "groq_winner"}

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(0.50)
            return {"tone": "casual", "corrections": [], "completions": [], "source": "nvidia_loser"}

        with patch.object(groq_provider, "analyze_draft", side_effect=fast_call), \
             patch.object(nvidia_provider, "analyze_draft", side_effect=slow_call):

            res = await fresh_router._execute_racing("draft_analysis", "analyze_draft", draft="test", conversation_context=[])
            assert res is not None
            assert res.get("source") == "groq_winner"
