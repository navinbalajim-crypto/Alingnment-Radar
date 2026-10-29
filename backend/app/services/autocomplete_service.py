"""AI-assisted writing suggestions for the chat composer.

Independent from alignment analysis: nothing here persists drafts, creates messages or findings.
Cost controls: explicit user consent, short-draft/terminal-punctuation skips, per-user rate limit,
TTL cache, and strict validation that suggestions extend the user's own text.
"""

import re
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.services.ai_router import ai_router

MIN_DRAFT_CHARS = 5
MAX_SUGGESTIONS = 3
MAX_SUGGESTION_CHARS = 240
COMPLETION_TIMEOUT_SECONDS = 3.0
CACHE_TTL_SECONDS = 120.0
CACHE_MAX_ENTRIES = 512
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60.0


def _norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text).lower()


class AutocompleteService:
    def __init__(self) -> None:
        self._cache: "OrderedDict[Tuple, Tuple[float, List[str]]]" = OrderedDict()
        self._hits: Dict[uuid.UUID, Deque[float]] = defaultdict(deque)

    def _allow(self, user_id: uuid.UUID) -> bool:
        now = time.monotonic()
        hits = self._hits[user_id]
        while hits and now - hits[0] > RATE_LIMIT_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_REQUESTS:
            return False
        hits.append(now)
        return True

    @staticmethod
    def eligible(draft: str) -> bool:
        stripped = draft.strip()
        # Whitespace-only/very short drafts and finished sentences never reach a provider.
        return len(stripped) >= MIN_DRAFT_CHARS and not re.search(r"[.!?]\s*$", stripped)

    @staticmethod
    def validate(draft: str, raw: object) -> List[str]:
        """Keep only suggestions that genuinely extend the user's draft (no meaning-changing rewrites)."""
        items = raw.get("suggestions") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        draft_norm = _norm(draft)
        # Allow tiny spelling/case fixes inside the typed prefix, but require the bulk to be preserved.
        anchor = draft_norm[: max(len(draft_norm) - 3, 1)]
        out: List[str] = []
        seen = set()
        for item in items:
            value = item.get("text") if isinstance(item, dict) else item
            text = value.strip() if isinstance(value, str) else ""
            key = _norm(text)
            if not text or len(text) > MAX_SUGGESTION_CHARS or key == draft_norm or key in seen:
                continue
            if not key.startswith(anchor) or len(key) <= len(draft_norm):
                continue
            seen.add(key)
            out.append(text)
            if len(out) == MAX_SUGGESTIONS:
                break
        return out

    async def suggest(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        draft: str,
        context: List[Dict[str, str]],
        consent: bool,
    ) -> Optional[List[str]]:
        """Return validated suggestions, [] when none, or None when AI was not (or could not be) used."""
        if not consent or not self.eligible(draft):
            return None

        last_id = context[-1].get("id", "") if context else ""
        key = (user_id, conversation_id, last_id, draft.strip().lower())
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            self._cache.move_to_end(key)
            return cached[1]

        if not self._allow(user_id):
            return None

        try:
            raw = await ai_router.suggest_completions(
                draft=draft, conversation_context=context, timeout=COMPLETION_TIMEOUT_SECONDS
            )
        except Exception as exc:  # router already swallows provider errors; belt and braces
            logger.info(f"Completion request failed: {type(exc).__name__}")
            return None
        if raw is None:
            return None

        result = self.validate(draft, raw)
        self._cache[key] = (now, result)
        while len(self._cache) > CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)
        return result


autocomplete_service = AutocompleteService()
