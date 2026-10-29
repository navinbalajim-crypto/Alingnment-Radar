"""Adaptive Latency-Aware AI Router orchestrating 3-way selection: Local, NVIDIA NIM, and Groq."""

import asyncio
from collections import deque
from enum import Enum
import math
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple
import uuid

from app.core.config import settings
from app.core.logging import logger
from app.providers.groq_provider import groq_provider
from app.providers.nebius_provider import nebius_provider
from app.providers.nvidia_provider import nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult, ResolutionEvaluationResult
from app.services.spelling_engine import evaluate_clarity_rules, get_spelling_corrections


class TaskType(str, Enum):
    DRAFT_ANALYSIS = "draft_analysis"
    ALIGNMENT_ANALYSIS = "alignment_analysis"
    RESOLUTION_EVALUATION = "resolution_evaluation"
    RECOMMENDATION_INTENT = "recommendation_intent"
    DRAFT_COMPLETION = "draft_completion"


class ProviderTaskStats:
    """Maintains latency window, EWMA, success/failure counts, and token usage per provider per task."""

    def __init__(self, max_samples: int = 20, ewma_alpha: float = 0.3):
        self.samples: Deque[float] = deque(maxlen=max_samples)
        self.ewma_latency_ms: Optional[float] = None
        self.ewma_alpha: float = ewma_alpha
        self.request_count: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.fallback_count: int = 0
        self.rate_limit_count: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

    def record_sample(
        self,
        latency_ms: float,
        success: bool,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.request_count += 1
        if success:
            self.success_count += 1
            # Simple outlier filter: don't let crazy spikes skew EWMA immediately
            if self.samples and len(self.samples) >= 3:
                median_lat = sorted(self.samples)[len(self.samples) // 2]
                if latency_ms > median_lat * 4.0:
                    # Clip outlier to 4x median for EWMA stability
                    clipped_ms = median_lat * 4.0
                else:
                    clipped_ms = latency_ms
            else:
                clipped_ms = latency_ms

            self.samples.append(latency_ms)
            if self.ewma_latency_ms is None:
                self.ewma_latency_ms = clipped_ms
            else:
                self.ewma_latency_ms = (
                    self.ewma_alpha * clipped_ms + (1.0 - self.ewma_alpha) * self.ewma_latency_ms
                )
        else:
            self.failure_count += 1

        if usage:
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "samples_count": len(self.samples),
            "recent_samples_ms": [round(s, 1) for s in list(self.samples)[-5:]],
            "ewma_latency_ms": round(self.ewma_latency_ms, 2) if self.ewma_latency_ms is not None else None,
            "requests": self.request_count,
            "successes": self.success_count,
            "failures": self.failure_count,
            "fallbacks": self.fallback_count,
            "rate_limits": self.rate_limit_count,
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
                "total": self.total_tokens,
            },
        }


class AIRouter:
    """
    Intelligent 3-way AI router dynamically coordinating:
    1. Local correction engine (instant, offline word-level spelling & high-confidence clarity templates)
    2. NVIDIA NIM Nemotron (deep conversational alignment, complex reasoning)
    3. Groq (ultra-low latency cloud inference with Llama-3.3-70b / Llama-3.1-8b)
    """

    def __init__(self):
        self.providers = {
            "nvidia": nvidia_provider,
            "groq": groq_provider,
            "nebius": nebius_provider,
        }
        # Stats per provider per task: Dict[provider, Dict[task_type, ProviderTaskStats]]
        self._stats: Dict[str, Dict[str, ProviderTaskStats]] = {
            "nvidia": {t.value: ProviderTaskStats() for t in TaskType},
            "groq": {t.value: ProviderTaskStats() for t in TaskType},
            "nebius": {t.value: ProviderTaskStats() for t in TaskType},
            "local": {t.value: ProviderTaskStats() for t in TaskType},
        }

        # Wire up latency observers on providers
        nvidia_provider.set_latency_observer(self._on_provider_latency)
        groq_provider.set_latency_observer(self._on_provider_latency)
        nebius_provider.set_latency_observer(self._on_provider_latency)

    def _on_provider_latency(
        self,
        provider_name: str,
        task_type: str,
        latency_ms: float,
        success: bool,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Callback invoked by providers after every completion with monotonic timing."""
        provider_stats = self._stats.get(provider_name)
        if provider_stats:
            task_stat = provider_stats.get(task_type)
            if not task_stat:
                task_stat = ProviderTaskStats()
                provider_stats[task_type] = task_stat
            task_stat.record_sample(latency_ms, success, usage)

    def select_cloud_provider(self, task_type: str) -> Tuple[str, str]:
        """
        Select fastest eligible cloud provider based on health, circuit breaker state,
        and measured EWMA latency for this specific task type.
        Returns: (selected_provider_name, explanation_reason)
        """
        strategy = (settings.AI_ROUTER_STRATEGY or "adaptive").lower()
        if strategy in ("nvidia", "nemotron"):
            return "nvidia", "Selected by forced strategy config (AI_ROUTER_STRATEGY=nvidia)"
        if strategy in ("groq", "groq_ai"):
            return "groq", "Selected by forced strategy config (AI_ROUTER_STRATEGY=groq)"
        if strategy == "nebius":
            if nebius_provider.is_configured():
                return "nebius", "Selected by forced strategy config (AI_ROUTER_STRATEGY=nebius)"
            logger.warning("[AIRouter] AI_ROUTER_STRATEGY=nebius but NEBIUS_API_KEY is not configured; using adaptive selection.")

        # Check configuration
        nv_configured = nvidia_provider.is_configured()
        groq_configured = groq_provider.is_configured()

        if not nv_configured and not groq_configured:
            return "none", "Neither NVIDIA nor Groq is configured with valid credentials."

        if nv_configured and not groq_configured:
            return "nvidia", "Only NVIDIA is configured."

        if groq_configured and not nv_configured:
            return "groq", "Only Groq is configured."

        # Both are configured; check circuit breaker health
        nv_health = nvidia_provider.check_health()
        groq_health = groq_provider.check_health()

        nv_healthy = nv_health.get("is_healthy", False)
        groq_healthy = groq_health.get("is_healthy", False)

        if nv_healthy and not groq_healthy:
            return "nvidia", f"Groq circuit open or in cooldown ({groq_health.get('last_error')}); NVIDIA selected."

        if groq_healthy and not nv_healthy:
            return "groq", f"NVIDIA circuit open or in cooldown ({nv_health.get('last_error')}); Groq selected."

        if not nv_healthy and not groq_healthy:
            # Both degraded; prefer whichever has lower consecutive failures or probe
            if nv_health.get("consecutive_failures", 0) <= groq_health.get("consecutive_failures", 0):
                return "nvidia", "Both providers degraded; attempting probe with NVIDIA."
            return "groq", "Both providers degraded; attempting probe with Groq."

        # Both are healthy! Check latency metrics for this task type
        # For interactive draft typing analysis, Groq provides sub-second responses (<800ms)
        if task_type == TaskType.DRAFT_ANALYSIS.value and groq_healthy:
            return "groq", "Groq selected for sub-second interactive draft analysis."

        nv_stats = self._stats["nvidia"].get(task_type)
        groq_stats = self._stats["groq"].get(task_type)

        nv_samples = len(nv_stats.samples) if nv_stats else 0
        groq_samples = len(groq_stats.samples) if groq_stats else 0
        min_samples = settings.AI_MIN_LATENCY_SAMPLES

        # If both have sufficient samples, compare EWMA latency
        if nv_samples >= min_samples and groq_samples >= min_samples:
            nv_ewma = nv_stats.ewma_latency_ms or float("inf")
            groq_ewma = groq_stats.ewma_latency_ms or float("inf")

            if groq_ewma < nv_ewma:
                return "groq", (
                    f"Groq measured faster for {task_type} "
                    f"(EWMA {groq_ewma:.1f}ms vs NVIDIA {nv_ewma:.1f}ms, Groq samples: {groq_samples}, NVIDIA samples: {nv_samples})"
                )
            else:
                return "nvidia", (
                    f"NVIDIA measured faster or equal for {task_type} "
                    f"(EWMA {nv_ewma:.1f}ms vs Groq {groq_ewma:.1f}ms, NVIDIA samples: {nv_samples}, Groq samples: {groq_samples})"
                )

        # Insufficient historical samples for one or both; gather baseline samples
        if groq_samples < min_samples:
            return "groq", f"Gathering baseline latency samples for Groq ({groq_samples}/{min_samples} samples collected)."
        if nv_samples < min_samples:
            return "nvidia", f"Gathering baseline latency samples for NVIDIA ({nv_samples}/{min_samples} samples collected)."

        return "nvidia", "Defaulting to NVIDIA."

    async def _execute_with_fallback(
        self,
        task_type: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Executes an AI task against the selected provider with monotonic timing and bounded fallback.
        At most one fallback attempt is made. No duplicate side effects.
        """
        selected_provider, reason = self.select_cloud_provider(task_type)
        logger.info(f"[AIRouter] Task={task_type} -> Selected={selected_provider} ({reason})")

        if selected_provider == "none":
            logger.info(f"[AIRouter] No cloud provider available for task {task_type}")
            return None

        # Check for optional racing mode if enabled
        strategy = (settings.AI_ROUTER_STRATEGY or "adaptive").lower()
        if (
            strategy == "adaptive"
            and settings.AI_RACING_ENABLED
            and nvidia_provider.is_configured()
            and groq_provider.is_configured()
        ):
            return await self._execute_racing(task_type, method_name, *args, **kwargs)

        primary = self.providers[selected_provider]
        fallback_name = "groq" if selected_provider == "nvidia" else "nvidia"
        fallback = self.providers[fallback_name]

        try:
            method = getattr(primary, method_name)
            result = await method(*args, **kwargs)
            if result is not None:
                return result
        except Exception as exc:
            logger.warning(
                f"[AIRouter] Primary provider {selected_provider} failed for task={task_type}: {exc}. "
                f"Attempting bounded fallback to {fallback_name}."
            )
            # Record fallback attempt in stats
            if selected_provider in self._stats and task_type in self._stats[selected_provider]:
                self._stats[selected_provider][task_type].fallback_count += 1

        # Fallback path (at most 1 bounded attempt, only when adaptive strategy is enabled)
        if strategy == "adaptive" and fallback.is_configured() and fallback.check_health().get("is_healthy", False):
            try:
                method = getattr(fallback, method_name)
                logger.info(f"[AIRouter] Executing fallback with {fallback_name} for task={task_type}")
                return await method(*args, **kwargs)
            except Exception as fb_exc:
                logger.error(f"[AIRouter] Fallback provider {fallback_name} also failed for task={task_type}: {fb_exc}")

        return None

    async def _execute_racing(
        self,
        task_type: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Optional race mode: runs both NVIDIA and Groq concurrently, returns the first valid response,
        cancelling the slower request. Strictly returns exactly 1 validated response.
        """
        logger.info(f"[AIRouter] RACING MODE: Dispatching task={task_type} to both NVIDIA and Groq")
        nv_task = asyncio.create_task(getattr(nvidia_provider, method_name)(*args, **kwargs))
        groq_task = asyncio.create_task(getattr(groq_provider, method_name)(*args, **kwargs))

        done, pending = await asyncio.wait(
            [nv_task, groq_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        winner_result = None
        for completed in done:
            try:
                res = completed.result()
                if res is not None:
                    winner_result = res
                    break
            except Exception as exc:
                logger.debug(f"[AIRouter] Race candidate failed: {exc}")

        # Cancel remaining pending task to prevent wasted resources
        for p in pending:
            p.cancel()

        if winner_result is not None:
            return winner_result

        # If the first completed was None or raised an error, wait for the pending one
        for p in pending:
            try:
                res = await p
                if res is not None:
                    return res
            except Exception as exc:
                logger.debug(f"[AIRouter] Pending race candidate failed: {exc}")

        return None

    # --- Public AI Task Interfaces with 3-Way Selection ---

    async def analyze_draft(
        self,
        draft: str,
        conversation_context: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Three-way draft analysis:
        1. Local model: Check high-confidence word typos and deterministic phrasing rules.
           If local check is complete and confidence >= 0.85, return immediately without API call!
        2. If draft needs sentence formation, contextual rewrites, or tone analysis, route to NVIDIA or Groq.
        3. If cloud providers fail, gracefully fall back to local corrections.
        """
        start_time = time.perf_counter()

        # Step 1: Run local spelling and deterministic clarity analysis
        local_corrections, local_rewritten = get_spelling_corrections(draft)
        clarity_rewrites = evaluate_clarity_rules(draft)

        # Check if local is sufficient (simple word typo with high confidence, no complex sentence context)
        has_local_data = bool(local_corrections or clarity_rewrites)
        is_cloud_available = nvidia_provider.is_configured() or groq_provider.is_configured()

        # If no cloud providers configured or user only typed simple word typos
        if not is_cloud_available and has_local_data:
            local_latency_ms = (time.perf_counter() - start_time) * 1000.0
            self._stats["local"][TaskType.DRAFT_ANALYSIS.value].record_sample(local_latency_ms, True)
            best_rewrite = clarity_rewrites[0]["suggested"] if clarity_rewrites else local_rewritten
            return {
                "tone": "mixed",
                "corrected_text": best_rewrite,
                "corrections": local_corrections,
                "completions": [],
                "source": "local_engine",
            }

        # Step 2: Route to fastest cloud provider for contextual enrichment
        cloud_result = await self._execute_with_fallback(
            TaskType.DRAFT_ANALYSIS.value,
            "analyze_draft",
            draft=draft,
            conversation_context=conversation_context,
            timeout=timeout,
        )

        if cloud_result:
            # Merge local high-confidence spelling additions if not already covered
            existing_origs = {
                str(c.get("original", "")).lower()
                for c in cloud_result.get("corrections", [])
                if isinstance(c, dict)
            }
            if "corrections" not in cloud_result or not isinstance(cloud_result["corrections"], list):
                cloud_result["corrections"] = []

            for lc in local_corrections:
                if lc["original"].lower() not in existing_origs:
                    cloud_result["corrections"].append(lc)

            # If clarity rewrite exists and cloud didn't suggest one, include it
            if clarity_rewrites and not cloud_result.get("corrected_text"):
                cloud_result["corrected_text"] = clarity_rewrites[0]["suggested"]

            return cloud_result

        # Step 3: Graceful fallback to local if cloud call failed or timed out
        if has_local_data:
            logger.info("[AIRouter] Cloud providers unavailable; falling back to local spelling/clarity engine.")
            best_rewrite = clarity_rewrites[0]["suggested"] if clarity_rewrites else local_rewritten
            return {
                "tone": "mixed",
                "corrected_text": best_rewrite,
                "corrections": local_corrections,
                "completions": [],
                "source": "local_fallback",
            }

        return None

    async def suggest_completions(
        self,
        draft: str,
        conversation_context: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Interactive autocomplete. Groq only (low latency, cheap); NVIDIA is deliberately never used
        for keystroke-driven completions. Returns None when Groq is unavailable so callers use local logic.
        """
        if not groq_provider.is_configured() or not groq_provider.check_health().get("is_healthy", False):
            return None
        # At most one retry, and only for an unparseable reply (provider errors are not retried).
        for _ in range(2):
            try:
                result = await groq_provider.suggest_completions(
                    draft=draft, conversation_context=conversation_context, timeout=timeout
                )
            except Exception as exc:
                logger.info(f"[AIRouter] Completion provider unavailable: {type(exc).__name__}")
                return None
            if result is not None:
                return result
        return None

    async def detect_alignment(
        self,
        conversation_context: List[Dict[str, Any]],
        valid_message_ids: Set[str],
        timeout: Optional[float] = None,
        established_context: Optional[List[Dict[str, Any]]] = None,
        target_message_ids: Optional[List[str]] = None,
    ) -> Optional[AlignmentAnalysisResult]:
        """Detect conversation ambiguities and misalignments via fastest eligible cloud provider."""
        return await self._execute_with_fallback(
            TaskType.ALIGNMENT_ANALYSIS.value,
            "detect_alignment",
            conversation_context=conversation_context,
            valid_message_ids=valid_message_ids,
            timeout=timeout,
            established_context=established_context,
            target_message_ids=target_message_ids,
        )

    async def evaluate_resolution(
        self,
        conversation_context: List[Dict[str, Any]],
        finding_info: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Optional[ResolutionEvaluationResult]:
        """Assess resolution of active alignment findings via fastest eligible cloud provider."""
        return await self._execute_with_fallback(
            TaskType.RESOLUTION_EVALUATION.value,
            "evaluate_resolution",
            conversation_context=conversation_context,
            finding_info=finding_info,
            timeout=timeout,
        )

    async def detect_recommendation_intent(
        self,
        conversation_context: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect external search recommendation intent via fastest eligible cloud provider."""
        return await self._execute_with_fallback(
            TaskType.RECOMMENDATION_INTENT.value,
            "detect_recommendation_intent",
            conversation_context=conversation_context,
            timeout=timeout,
        )

    def get_routing_stats(self) -> Dict[str, Any]:
        """Return diagnostic metrics without exposing API keys or user content."""
        return {
            "strategy": settings.AI_ROUTER_STRATEGY,
            "racing_enabled": settings.AI_RACING_ENABLED,
            "providers": {
                "nvidia": nvidia_provider.check_health(),
                "groq": groq_provider.check_health(),
                "nebius": nebius_provider.check_health(),
            },
            "task_metrics": {
                provider: {task: stats.to_dict() for task, stats in task_map.items()}
                for provider, task_map in self._stats.items()
            },
        }


ai_router = AIRouter()
