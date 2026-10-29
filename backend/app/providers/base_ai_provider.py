"""Base AI provider interface and common functionality for cloud LLM inference."""

import abc
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import httpx
from app.core.config import settings
from app.core.errors import ProviderError, ProviderUnavailableError, RateLimitError
from app.core.logging import logger
from app.schemas.ai import AlignmentAnalysisResult, AlignmentFindingItem, ResolutionEvaluationResult

DRAFT_TIMEOUT_SECONDS = 12.0




class BaseAIProvider(abc.ABC):
    """
    Standardized abstract base class for AI providers (NVIDIA, Groq, etc.).
    Includes circuit breaker, monotonic latency measurement, error classification,
    and schema normalization.
    """

    def __init__(
        self,
        provider_name: str,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.provider_name = provider_name
        self._client = client
        self.circuit_state: str = "closed"  # "closed" | "open" | "half-open"
        self.consecutive_failures: int = 0
        self.cooldown_until: float = 0.0
        self.last_error: Optional[str] = None
        self._latency_observer: Optional[Callable[[str, str, float, bool, Optional[Dict[str, Any]]], None]] = None

    def set_latency_observer(
        self,
        observer: Callable[[str, str, float, bool, Optional[Dict[str, Any]]], None],
    ) -> None:
        """Register an observer callback (e.g. router) to receive latency & token metrics."""
        self._latency_observer = observer

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials and endpoints for this provider are configured."""
        pass

    @abc.abstractmethod
    def get_model_name(self) -> str:
        """Return the active configured model name for this provider."""
        pass

    @abc.abstractmethod
    def get_base_url(self) -> str:
        """Return the active base URL for this provider."""
        pass

    @abc.abstractmethod
    def get_api_key(self) -> str:
        """Return API key."""
        pass

    @abc.abstractmethod
    def get_default_timeout(self) -> float:
        """Return default request timeout in seconds."""
        pass

    def _ensure_configured(self) -> None:
        """Validate provider configuration or raise ProviderUnavailableError."""
        if not self.is_configured():
            raise ProviderUnavailableError(self.provider_name, "API key or endpoint not configured.")

    def check_health(self) -> Dict[str, Any]:
        """
        Check provider health, handling circuit breaker state transitions.
        Transitions 'open' -> 'half-open' after cooldown period expires.
        """
        now = time.monotonic()
        if self.circuit_state == "open" and now >= self.cooldown_until:
            self.circuit_state = "half-open"

        is_healthy = self.is_configured() and self.circuit_state in ("closed", "half-open")
        return {
            "provider": self.provider_name,
            "model": self.get_model_name() if self.is_configured() else "unconfigured",
            "is_configured": self.is_configured(),
            "is_healthy": is_healthy,
            "circuit_state": self.circuit_state,
            "consecutive_failures": self.consecutive_failures,
            "cooldown_remaining_seconds": max(0.0, self.cooldown_until - now) if self.circuit_state == "open" else 0.0,
            "last_error": self.last_error,
        }

    def _record_success(self) -> None:
        """Reset circuit breaker and failure counts on successful response."""
        self.circuit_state = "closed"
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.last_error = None

    def _record_failure(self, exc: Exception, is_rate_limit: bool = False) -> None:
        """Record failure, increment counter, and trip circuit breaker if threshold reached."""
        self.consecutive_failures += 1
        self.last_error = str(exc)

        trip_threshold = settings.AI_CIRCUIT_BREAKER_FAILURES
        cooldown_duration = settings.AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS

        if is_rate_limit or self.consecutive_failures >= trip_threshold:
            self.circuit_state = "open"
            self.cooldown_until = time.monotonic() + cooldown_duration
            logger.warning(
                f"[{self.provider_name}] Circuit breaker OPEN for {cooldown_duration}s. "
                f"Failures: {self.consecutive_failures}, RateLimit: {is_rate_limit}, Error: {exc}"
            )

    async def _post_chat_completion(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "general",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute chat completion with monotonic latency instrumentation, timeout handling,
        and circuit breaker protection.
        """
        if not self.is_configured():
            raise ProviderUnavailableError(self.provider_name, "API key or endpoint not configured.")

        # Check circuit breaker
        now = time.monotonic()
        if self.circuit_state == "open" and now < self.cooldown_until:
            remaining = self.cooldown_until - now
            raise ProviderUnavailableError(
                self.provider_name,
                f"Circuit breaker is open (cooldown: {remaining:.1f}s remaining)."
            )

        timeout_sec = timeout or self.get_default_timeout()
        base_url = self.get_base_url().rstrip("/")
        endpoint = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.get_api_key()}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.get_model_name(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        merged_extra: Dict[str, Any] = {}
        if self.provider_name in ("nvidia", "nebius"):
            merged_extra["chat_template_kwargs"] = {"enable_thinking": False}
        if extra_body:
            merged_extra.update(extra_body)
        if merged_extra:
            payload.update(merged_extra)

        start_time = time.perf_counter()
        success = False
        usage_info: Optional[Dict[str, Any]] = None
        latency_ms = 0.0

        try:
            if self._client:
                response = await self._client.post(
                    endpoint, json=payload, headers=headers, timeout=timeout_sec
                )
            else:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    response = await client.post(endpoint, json=payload, headers=headers)

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if response.status_code == 429:
                logger.warning(f"[{self.provider_name}] Rate limited (HTTP 429)")
                exc = RateLimitError(f"{self.provider_name} rate limit exceeded.")
                self._record_failure(exc, is_rate_limit=True)
                raise exc

            if response.status_code >= 400:
                logger.error(f"[{self.provider_name}] HTTP {response.status_code}: (body omitted)")
                exc = ProviderError(self.provider_name, f"Inference failed with HTTP {response.status_code}")
                self._record_failure(exc)
                raise exc

            data = response.json()
            usage_info = data.get("usage")
            self._record_success()
            success = True
            return data

        except httpx.TimeoutException as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"[{self.provider_name}] Request timed out after {timeout_sec}s")
            p_exc = ProviderError(self.provider_name, f"Inference request timed out after {timeout_sec}s.")
            self._record_failure(p_exc)
            raise p_exc
        except (RateLimitError, ProviderError, ProviderUnavailableError):
            raise
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"[{self.provider_name}] Network/client error: {exc}")
            p_exc = ProviderError(self.provider_name, f"Network error: {exc}")
            self._record_failure(p_exc)
            raise p_exc
        finally:
            if self._latency_observer:
                try:
                    self._latency_observer(self.provider_name, task_type, latency_ms, success, usage_info)
                except Exception as obs_exc:
                    logger.debug(f"Error in latency observer: {obs_exc}")

    def _extract_json_from_response(self, response_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Safely extract and parse JSON object from OpenAI-compatible choice response."""
        choices = response_data.get("choices", [])
        if not choices:
            return None

        msg_obj = choices[0].get("message", {})
        raw_content = msg_obj.get("content") or msg_obj.get("reasoning_content") or ""
        if not isinstance(raw_content, str):
            raw_content = str(raw_content)
        raw_content = raw_content.strip()

        # Try to find JSON within markdown code blocks or between braces
        json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if not json_match and msg_obj.get("reasoning_content"):
            reasoning = str(msg_obj.get("reasoning_content"))
            json_match = re.search(r"\{.*\}", reasoning, re.DOTALL)

        if not json_match:
            finish_reason = choices[0].get("finish_reason")
            if finish_reason == "length":
                # Reasoning models (e.g. Nemotron with thinking enabled) can spend the entire
                # max_tokens budget on internal reasoning before emitting an answer, leaving
                # content empty. This is a truncated non-answer, not "nothing to say" -
                # never treated as success; the caller already receives None either way.
                logger.warning(
                    f"[{self.provider_name}] Response truncated by max_tokens before producing an answer "
                    f"(finish_reason=length, {len(raw_content)} chars of content)."
                )
            else:
                logger.warning(f"[{self.provider_name}] Could not extract JSON object from response ({len(raw_content)} chars)")
            return None

        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                return parsed
            return None
        except Exception as exc:
            logger.error(f"[{self.provider_name}] Failed to parse JSON from output: {exc}")
            return None

    # --- Standardized Task Execution Methods ---

    async def detect_alignment(
        self,
        conversation_context: List[Dict[str, Any]],
        valid_message_ids: Set[str],
        timeout: Optional[float] = None,
        established_context: Optional[List[Dict[str, Any]]] = None,
        target_message_ids: Optional[List[str]] = None,
    ) -> Optional[AlignmentAnalysisResult]:
        """
        Analyze conversation for perspective divergences, ambiguous commitments, or missing details.
        Supports returning zero, one, or multiple distinct findings and explicitly tracking
        which messages were analyzed.
        """
        self._ensure_configured()
        system_prompt = (
            "You are Alignment Radar, an AI specialized in detecting communication ambiguities, missing context, and misalignments in team chat.\n"
            "Analyze the conversation history, with special attention to any target messages specified.\n\n"
            "Look for:\n"
            "1. Ambiguous deadlines or timing (e.g., 'tomorrow', 'soon', 'later') where exact date, time, or timezone is unstated.\n"
            "2. Unclear or ambiguous references (e.g., 'the final version', 'that one', 'do it like before') where the specific document, file, or version is unspecified.\n"
            "3. Missing essential details (deadline, format, owner, scope, acceptance criteria).\n"
            "4. Conflicting expectations, misunderstandings, or unverified assumptions between participants.\n"
            "5. Explicit disagreements, contradictions, or decisions needing confirmation.\n\n"
            "CRITICAL RULES:\n"
            "- You may return ZERO, ONE, or MULTIPLE distinct findings in the 'findings' array.\n"
            "- If a batch of messages contains multiple genuinely distinct ambiguities (e.g., one message has a vague deadline, another has an unspecified file), create a separate finding entry for EACH distinct issue.\n"
            "- Do NOT merge genuinely distinct ambiguities merely because they occur in the same conversation or batch.\n"
            "- Do NOT create multiple findings for different phrasings of the same underlying issue.\n"
            "- Casual greetings or acknowledgements (e.g., 'Hi', 'OK', 'Thanks', 'LOL', 'cool', 'sounds good') must NOT generate unnecessary findings when appropriate to context.\n"
            "- In 'analyzed_message_ids', list ALL message IDs that were considered and reviewed during this analysis.\n"
            "- If the conversation is clear, aligned, or standard acknowledgment, set 'findings': [] and list reviewed message IDs in 'analyzed_message_ids'.\n"
            "- Only reference message IDs that explicitly appear in the conversation history provided.\n"
            "- Never invent message IDs or pretend to know private mental states.\n"
            "- ESTABLISHED CONTEXT lists issues the participants already resolved and their confirmed answers. Never report those issues again and treat confirmed answers as known facts. Only report a NEW ambiguity or a direct contradiction of an established answer.\n"
            "- Formulate a constructive, neutral clarification question for each finding.\n"
            "- Provide a helpful suggested_reply and intended_outcome.\n\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "analyzed_message_ids": [array of string message IDs considered],\n'
            '  "findings": [\n'
            "    {\n"
            '      "mismatch_detected": true,\n'
            '      "category": "ambiguity" | "deadlines" | "scope" | "goals" | "responsibilities" | "definition_of_done" | "conflicting_interpretations" | "unclear_references" | "missing_details" | "other",\n'
            '      "severity": "low" | "medium" | "high",\n'
            '      "title": string,\n'
            '      "explanation": string,\n'
            '      "confidence": number between 0.0 and 1.0,\n'
            '      "supporting_message_ids": [array of string message IDs providing evidence for this specific finding],\n'
            '      "clarification_question": string or null,\n'
            '      "suggested_reply": string or null,\n'
            '      "suggested_rewrite": string or null,\n'
            '      "intended_outcome": string or null\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        formatted_messages = "\n".join(
            [
                f"[ID: {msg.get('id', 'N/A')}] [{msg.get('sender_username', 'Unknown')}]: {msg.get('content', '')}"
                for msg in conversation_context
            ]
        )

        established_block = ""
        if established_context:
            lines = [
                f"- Resolved issue: {e.get('issue', '')} | Confirmed answer: {e.get('confirmed_answer') or 'confirmed by participants'}"
                for e in established_context
            ]
            established_block = "ESTABLISHED CONTEXT (already resolved, do not re-report):\n" + "\n".join(lines) + "\n\n"

        target_block = ""
        if target_message_ids:
            target_ids_set = set(target_message_ids)
            target_lines = [
                f"- [ID: {msg.get('id')}] [{msg.get('sender_username', 'User')}]: {msg.get('content')}"
                for msg in conversation_context
                if str(msg.get("id")) in target_ids_set
            ]
            if target_lines:
                target_block = "TARGET MESSAGES TO ANALYZE IN THIS BATCH (evaluate each one; must be accounted for in analyzed_message_ids):\n" + "\n".join(target_lines) + "\n\n"

        user_prompt = f"{established_block}{target_block}Analyze the following conversation messages for potential ambiguity or misalignment:\n\n{formatted_messages}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response_data = await self._post_chat_completion(
            messages=messages,
            task_type="alignment_analysis",
            temperature=0.1,
            max_tokens=2048,
            timeout=timeout,
        )

        parsed = self._extract_json_from_response(response_data)
        if not parsed:
            return None

        try:
            # Check if modern multi-finding schema was returned
            raw_findings = parsed.get("findings")
            raw_analyzed_ids = parsed.get("analyzed_message_ids", [])
            # A reply that is valid JSON but has none of the expected fields is malformed, not "no issues".
            if not isinstance(raw_findings, list) and "mismatch_detected" not in parsed:
                logger.warning(f"[{self.provider_name}] Alignment reply missing findings/coverage; treating as failure.")
                return None
            clean_analyzed_ids = [str(mid) for mid in raw_analyzed_ids if str(mid) in valid_message_ids]

            cleaned_items: List[AlignmentFindingItem] = []

            if isinstance(raw_findings, list):
                for f_data in raw_findings:
                    if not isinstance(f_data, dict):
                        continue
                    mismatch = bool(f_data.get("mismatch_detected", True))
                    if not mismatch:
                        continue

                    raw_supp = f_data.get("supporting_message_ids", [])
                    clean_supp = [str(mid) for mid in raw_supp if str(mid) in valid_message_ids]
                    conf = float(f_data.get("confidence", 0.0))

                    # Suppress false alarms with zero grounded evidence or very low confidence
                    if not clean_supp or conf < 0.4:
                        continue

                    cat = f_data.get("category") or "ambiguity"
                    title = f_data.get("title") or f"{cat.replace('_', ' ').title()} Detected"
                    expl = str(f_data.get("explanation", "")).strip() or "Ambiguity detected"
                    suggested_reply = f_data.get("suggested_reply") or f_data.get("suggested_rewrite")

                    cleaned_items.append(
                        AlignmentFindingItem(
                            mismatch_detected=True,
                            category=cat,
                            severity=str(f_data.get("severity", "medium")),
                            title=title,
                            explanation=expl,
                            confidence=conf,
                            supporting_message_ids=clean_supp,
                            clarification_question=f_data.get("clarification_question"),
                            suggested_reply=suggested_reply,
                            suggested_rewrite=f_data.get("suggested_rewrite"),
                            intended_outcome=f_data.get("intended_outcome"),
                        )
                    )
            elif "mismatch_detected" in parsed:
                # Legacy single-finding schema fallback
                mismatch = bool(parsed.get("mismatch_detected", False))
                raw_supp = parsed.get("supporting_message_ids", [])
                clean_supp = [str(mid) for mid in raw_supp if str(mid) in valid_message_ids]
                conf = float(parsed.get("confidence", 0.0))

                if mismatch and clean_supp and conf >= 0.4:
                    cat = parsed.get("category") or "ambiguity"
                    title = parsed.get("title") or f"{cat.replace('_', ' ').title()} Detected"
                    expl = str(parsed.get("explanation", "")).strip() or "Ambiguity detected"
                    suggested_reply = parsed.get("suggested_reply") or parsed.get("suggested_rewrite")

                    cleaned_items.append(
                        AlignmentFindingItem(
                            mismatch_detected=True,
                            category=cat,
                            severity=str(parsed.get("severity", "medium")),
                            title=title,
                            explanation=expl,
                            confidence=conf,
                            supporting_message_ids=clean_supp,
                            clarification_question=parsed.get("clarification_question"),
                            suggested_reply=suggested_reply,
                            suggested_rewrite=parsed.get("suggested_rewrite"),
                            intended_outcome=parsed.get("intended_outcome"),
                        )
                    )
                    if not clean_analyzed_ids:
                        clean_analyzed_ids = list(clean_supp)

            # Coverage that cites only unknown message IDs proves nothing was reviewed.
            if (
                isinstance(raw_findings, list) and not cleaned_items and not clean_analyzed_ids
                and isinstance(raw_analyzed_ids, list) and raw_analyzed_ids
            ):
                logger.warning(f"[{self.provider_name}] Coverage cited no valid message IDs; treating as failure.")
                return None

            # Ensure all supporting IDs are counted as analyzed
            for item in cleaned_items:
                for mid in item.supporting_message_ids:
                    if mid not in clean_analyzed_ids:
                        clean_analyzed_ids.append(mid)

            return AlignmentAnalysisResult(
                mismatch_detected=len(cleaned_items) > 0,
                findings=cleaned_items,
                analyzed_message_ids=clean_analyzed_ids,
            )
        except Exception as exc:
            logger.error(f"[{self.provider_name}] Failed to validate AlignmentAnalysisResult: {exc}")
            return None


    async def evaluate_resolution(
        self,
        conversation_context: List[Dict[str, Any]],
        finding_info: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Optional[ResolutionEvaluationResult]:
        """
        Evaluate whether recent messages resolve an active alignment finding.
        Casual acknowledgments strictly do NOT resolve ambiguities.
        """
        self._ensure_configured()
        system_prompt = (
            "You are Alignment Radar's Resolution Evaluator.\n"
            "You are assessing whether a previously detected communication misalignment has been substantively resolved by the participants.\n\n"
            "CRITICAL RESOLUTION RULES:\n"
            "1. Casual acknowledgments (e.g., 'ok', 'okay', 'fine', 'sure', 'got it', 'cool', 'sounds good', 'yes', 'k', 'noted', 'agree') "
            "DO NOT constitute resolution evidence. If users only exchanged casual acknowledgments, set has_resolution_evidence=false and status_update='clarifying'.\n"
            "2. Resolution requires CONCRETE SUBSTANCE addressing the specific ambiguity or misunderstanding. For example: providing a specific date/time with timezone, "
            "specifying exact file versions/links, explicit confirmation of owners/responsibilities, or clear operational definitions.\n"
            "3. If concrete substance has been provided by one or more participants that answers the clarification question or fixes the misunderstanding:\n"
            "   - set has_resolution_evidence=true\n"
            "   - set is_resolved=true\n"
            "   - set status_update='awaiting_confirmation' (requiring participants to confirm) or 'resolved' if both parties explicitly validated the concrete terms.\n"
            "   - provide evidence_summary citing the specific clarification given.\n"
            "4. If conversation has drifted without clarifying the issue, keep status_update='clarifying' or 'unresolved' with has_resolution_evidence=false.\n\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "has_resolution_evidence": boolean,\n'
            '  "is_resolved": boolean,\n'
            '  "status_update": "clarifying" | "awaiting_confirmation" | "resolved" | "unresolved",\n'
            '  "evidence_summary": string or null,\n'
            '  "confidence": number between 0.0 and 1.0\n'
            "}"
        )

        formatted_messages = "\n".join(
            [
                f"[ID: {msg.get('id', 'N/A')}] [{msg.get('sender_username', 'User')}]: {msg.get('content', '')}"
                for msg in conversation_context
            ]
        )

        user_prompt = (
            f"Original Alignment Issue:\n"
            f"- Title: {finding_info.get('title', 'Misalignment')}\n"
            f"- Category: {finding_info.get('category', 'ambiguity')}\n"
            f"- Explanation: {finding_info.get('explanation', '')}\n"
            f"- Clarification Question: {finding_info.get('clarification_question', 'N/A')}\n\n"
            f"Recent Conversation:\n"
            f"{formatted_messages}\n\n"
            f"Has this specific issue been substantively clarified with concrete details?"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response_data = await self._post_chat_completion(
            messages=messages,
            task_type="resolution_evaluation",
            temperature=0.1,
            max_tokens=1024,
            timeout=timeout,
        )

        parsed = self._extract_json_from_response(response_data)
        if not parsed:
            return None

        try:
            return ResolutionEvaluationResult(
                has_resolution_evidence=bool(parsed.get("has_resolution_evidence", False)),
                is_resolved=bool(parsed.get("is_resolved", False)),
                status_update=str(parsed.get("status_update", "clarifying")),
                evidence_summary=parsed.get("evidence_summary"),
                confidence=float(parsed.get("confidence", 0.0)),
            )
        except Exception as exc:
            logger.error(f"[{self.provider_name}] Failed to validate ResolutionEvaluationResult: {exc}")
            return None

    async def detect_recommendation_intent(
        self,
        conversation_context: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Analyze conversation to identify external search recommendations."""
        self._ensure_configured()
        system_prompt = (
            "You are an intelligent search intent extractor for a team chat application.\n"
            "Analyze the conversation to determine if participants are discussing topics where external contextual recommendations "
            "would be helpful. Supported domains are:\n"
            "1. Music (Tamil songs, film tracks, albums, artists, Spotify tracks, YouTube music)\n"
            "2. Cricket (IPL, World Cup, cricket news, match highlights, scores, player stats)\n"
            "3. Movies / Media (movie recommendations, trailers, films)\n"
            "4. Places / Travel (places to visit, restaurants, attractions, travel)\n"
            "5. Shopping / Websites (a request for a specific website, an official site, or where to buy a "
            "product online -- e.g. \"give me a bangles website\", \"find a website to buy shoes\", "
            "\"official website for NVIDIA\")\n"
            "6. Web topics / News (technical tutorials, articles, current events not covered above)\n\n"
            "Rules:\n"
            "- Only trigger intent if participants are actively mentioning, asking for, or discussing specific tracks, artists, matches, movies, places, websites, products, or topics.\n"
            "- Do NOT trigger intent for generic greetings or casual banter.\n"
            "- A request for a website, an official site, or where to buy something is Shopping/Websites, "
            "never Music -- do not default to music when you are unsure.\n"
            "- Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "has_intent": boolean,\n'
            '  "category": "music" | "cricket" | "movie" | "place" | "shopping" | "web" | null,\n'
            '  "query": string (precise search query for YouTube, Spotify, or Tavily),\n'
            '  "preferred_providers": ["youtube" | "spotify" | "tavily"]\n'
            "}"
        )

        formatted_messages = "\n".join(
            [
                f"[{msg.get('sender_username', 'User')}]: {msg.get('content', '')}"
                for msg in conversation_context[-10:]
            ]
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract search intent from recent chat:\n\n{formatted_messages}"},
        ]

        response_data = await self._post_chat_completion(
            messages=messages,
            task_type="recommendation_intent",
            temperature=0.1,
            max_tokens=1024,
            timeout=timeout,
        )

        parsed = self._extract_json_from_response(response_data)
        if not parsed:
            return None

        try:
            if parsed.get("has_intent") and parsed.get("query"):
                category = parsed.get("category", "web")
                preferred = parsed.get("preferred_providers")
                if not preferred:
                    if category == "music":
                        preferred = ["youtube", "spotify"]
                    elif category == "cricket":
                        preferred = ["tavily", "youtube"]
                    elif category == "shopping":
                        preferred = ["tavily"]
                    else:
                        preferred = ["tavily", "youtube"]

                return {
                    "has_intent": True,
                    "category": category,
                    "query": str(parsed.get("query")).strip(),
                    "preferred_providers": preferred,
                }
            return None
        except Exception as exc:
            logger.error(f"[{self.provider_name}] Failed to parse recommendation intent: {exc}")
            return None

    async def suggest_completions(
        self,
        draft: str,
        conversation_context: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Low-latency continuation suggestions for a partially typed chat message."""
        self._ensure_configured()
        formatted_messages = "\n".join(
            f"[{msg.get('sender_username', 'User')}]: {str(msg.get('content', ''))[:200]}"
            for msg in conversation_context[-6:]
        )
        system_prompt = (
            "You are an autocomplete engine inside a team chat composer.\n"
            "Given the user's partial message and recent chat, propose up to 3 ways to continue it.\n"
            "Rules:\n"
            "- Every suggestion must be the user's full text so far, corrected only for obvious spelling/capitalisation, followed by a natural continuation.\n"
            "- Complete a partially typed last word when it is clearly incomplete.\n"
            "- Keep suggestions short, natural and professional. Vary length: a phrase, a short sentence.\n"
            "- NEVER invent dates, times, names, numbers, files or commitments that are not in the draft or chat. Use neutral wording instead.\n"
            "- Do not change the user's meaning.\n"
            'Return ONLY JSON: {"suggestions": [{"text": "full suggested message"}]}'
        )
        user_prompt = f"Recent conversation:\n{formatted_messages}\n\nPartial draft:\n{draft}"
        extra_body: Optional[Dict[str, Any]] = None
        # Disables the model's chain-of-thought reasoning tokens. Verified live against Nebius
        # (reasoning otherwise consumed the entire max_tokens budget before any answer, returning
        # empty/truncated content) in addition to NVIDIA NIM.
        if self.provider_name in ("nvidia", "nebius"):
            extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
        elif self.provider_name == "groq":
            extra_body = {"response_format": {"type": "json_object"}}
            if "gpt-oss" in self.get_model_name().lower():
                extra_body["reasoning_effort"] = "low"
        response_data = await self._post_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            task_type="draft_completion",
            temperature=0.3,
            max_tokens=400,
            extra_body=extra_body,
            timeout=timeout,
        )
        return self._extract_json_from_response(response_data)

    async def analyze_draft(
        self,
        draft: str,
        conversation_context: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze user draft for contextual tone, sentence formation, grammar, and completions.
        Preserves names, abbreviations, and user intent.
        """
        self._ensure_configured()
        formatted_messages = "\n".join(
            [
                f"[{msg.get('sender_username', 'User')}]: {msg.get('content', '')}"
                for msg in conversation_context[-8:]
            ]
        )

        system_prompt = (
            "You are a writing assistant embedded in a team chat application.\n"
            "Analyze the user's current draft message and the recent conversation context.\n\n"
            "Rules:\n"
            "1. Detect the conversation tone (professional, casual, academic, mixed).\n"
            "2. Correct genuine misspellings of real words (e.g. 'elaphant' -> 'elephant', 'misic' -> 'music', "
            "'recomend' -> 'recommend', 'didnot' -> 'did not', 'afterrnoon' -> 'afternoon', 'hsa' -> 'has', 'doesnot' -> 'does not') and clear grammar errors.\n"
            "3. For clumsy or ungrammatical draft phrasing, suggest a natural rewrite in 'corrected_text'. "
            "Example: 'tomorrow is submission' -> 'The submission is due tomorrow.'\n"
            "4. NEVER invent missing information or ask questions unless genuinely needed in context. "
            "If a statement is clear (e.g. 'Tomorrow is the submission deadline.', 'Make it simple.', 'Use the final version.', 'Okay.', 'I will finish it soon.'), "
            "do NOT treat it as incomplete or ask whether it is morning or afternoon.\n"
            "5. If previous context asked for missing information and draft lacks it, suggest clarification. Otherwise, do not interrupt.\n"
            "6. Intentional slang ('lol', 'bro', 'ngl', 'gonna', 'u') are NOT mistakes in casual tone.\n"
            "7. Expand informal abbreviations ('tmrw' -> 'tomorrow', 'bcoz' -> 'because', 'pls' -> 'please') when appropriate.\n"
            "8. Never change names, dates, numbers, technical terms, or the user's intended meaning.\n"
            "9. If the draft looks unfinished, suggest up to 2 short completions starting with user's words. Otherwise return [].\n"
            "10. If nothing needs fixing, corrections is [] and corrected_text is null.\n\n"
            "Return ONLY a valid JSON object:\n"
            "{\n"
            '  "tone": "professional" | "casual" | "academic" | "mixed",\n'
            '  "corrected_text": string or null,\n'
            '  "corrections": [\n'
            '    {"original": "misspelled word", "corrected": "correction", "reason": "brief reason", "confidence": 0.0-1.0}\n'
            "  ],\n"
            '  "completions": [\n'
            '    {"text": "suggested completion", "confidence": 0.0-1.0}\n'
            "  ]\n"
            "}"
        )

        user_prompt = f"Recent conversation:\n{formatted_messages}\n\nCurrent draft:\n{draft}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        extra_body: Optional[Dict[str, Any]] = None
        # Disables chain-of-thought reasoning tokens for low latency; verified live against
        # Nebius as well as NVIDIA NIM (see suggest_completions for details).
        if self.provider_name in ("nvidia", "nebius"):
            extra_body = {"chat_template_kwargs": {"enable_thinking": False}}

        response_data = await self._post_chat_completion(
            messages=messages,
            task_type="draft_analysis",
            temperature=0.1,
            max_tokens=600,
            extra_body=extra_body,
            timeout=timeout or DRAFT_TIMEOUT_SECONDS,
        )

        parsed = self._extract_json_from_response(response_data)
        if not parsed:
            return None

        try:
            return {
                "tone": parsed.get("tone", "mixed"),
                "corrected_text": parsed.get("corrected_text"),
                "corrections": parsed.get("corrections", []),
                "completions": parsed.get("completions", []),
            }
        except Exception as exc:
            logger.error(f"[{self.provider_name}] Failed to validate draft analysis: {exc}")
            return None
