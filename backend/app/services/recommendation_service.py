"""Contextual recommendation service integrating external search and user sharing."""

import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import logger
from app.models.recommendation import RecommendationItem
from app.providers.spotify_provider import spotify_provider
from app.providers.tavily_provider import tavily_provider
from app.providers.youtube_provider import youtube_provider
from app.repositories.ai_repo import AiRepository
from app.services.ai_router import ai_router
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.ai import RecommendationItemResponse
from app.schemas.message import MessageCreate, MessageRead
from app.services.conversation_service import ConversationService

# Cooldown tracking per conversation
_last_recommendation_time: Dict[uuid.UUID, float] = {}

# In-memory search results cache: (category, query, providers) -> (timestamp, results) with 60s TTL
_recommendations_cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}

# Only surface recommendations triggered by the recent part of the conversation, so cards
# for a topic the chat has moved on from don't keep reappearing on reload.
RECENT_MESSAGE_WINDOW = 20
RECENT_RECOMMENDATION_LIMIT = 6

import re


REQUEST_PREFIXES = r"^(?:(?:can|could)\s+you\s+(?:please\s+)?(?:recommend|recomend|suggest|play|give(?:\s+me|\s+us)?|share|send|find|get|show)|please\s+(?:recommend|recomend|suggest|play|give(?:\s+me|\s+us)?|share|send|find|get|show)|i\s+(?:want|would\s+like)\s+to\s+(?:listen\s+to|watch|hear|find|get|see)|i\s+need\s+(?:some\s+)?(?:recommendations?\s+for|suggestions?\s+for|links?\s+for|websites?\s+for)|i\s+(?:like|love)\s+|listen\s+to\s+|have\s+you\s+heard\s+|check\s+out\s+|suggest\s+(?:some\s+)?(?:good\s+)?|recommend\s+(?:some\s+)?(?:good\s+)?|give\s+(?:me\s+|us\s+)?(?:some\s+)?(?:recommendations?\s+for\s+|suggestions?\s+for\s+|links?\s+(?:for|to)\s+|websites?\s+(?:for|to)\s+)?|any\s+(?:good\s+)?(?:recommendations?\s+for\s+|suggestions?\s+for\s+|links?\s+(?:for|to)\s+|websites?\s+(?:for|to)\s+)?|what\s+are\s+some\s+good\s+|what\s+music\s+do\s+you\s+recommend|play\s+)"


def extract_contextual_draft_intent(text: str, recent_context: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Detect search intent and extract entities from the active composer draft,
    using recent conversation messages for contextual continuity.
    Handles music artists, Spotify discussions, movies, cricket, and suppresses unrelated topics.
    """
    if not text or len(text.strip()) < 3:
        return None
    clean = text.strip()
    clean_lower = clean.lower()

    # 0. Suppress negative commands and meta-feedback
    negation_patterns = [
        r"\b(?:don'?t|do\s+not|stop|never|not|no)\s+(?:recommend|recomend|suggest|play|listen|send|want)\b",
        r"\b(?:other\s*wise|otherwise)\s+(?:don'?t|do\s+not)\b",
        r"\b(?:don'?t|do\s+not)\s+(?:recommend|recomend)\s+(?:music|songs?)\b",
        r"\b(?:these\s+are\s+mistakes|fix\s+that|changes\s+automatically|chat\s+monitor)\b",
        r"\bwhen\s+i\s+talk\s+about\s+.*?\s+then\s+only\b",
    ]
    if any(re.search(pat, clean_lower) for pat in negation_patterns):
        return None

    # 1. Suppress common greetings and acknowledgments
    if clean_lower in {"hi", "hello", "hey", "ok", "okay", "thanks", "sure", "cool", "got it", "yes", "no", "bye"}:
        return None

    # 1b. Suppress past-action casual mentions of a song without request or question
    past_casual_song_patterns = [
        r"\b(?:yesterday|last night|earlier|previously)\b.*?\b(?:played|heard|sang|listened to)\s+(?:a\s+)?song\b",
        r"\b(?:my\s+friend|someone|he|she|they|friend)\s+(?:played|heard|sang|listened to|was\s+playing)\s+(?:a\s+)?song\b",
        r"^yesterday\s+.*?\s+song[!.?]*$",
    ]
    if any(re.search(pat, clean_lower) for pat in past_casual_song_patterns):
        if not any(req in clean_lower for req in ["suggest", "recommend", "which", "what", "send me", "link"]):
            return None

    # 2. Suppress focused technical/deadline/project discussions unless explicit media keywords present
    work_signals = [
        "deadline", "project", "submission", "submitting", "sprint", "deliverable",
        "finish the project", "budget", "meeting", "deploy", "jira", "code review",
        "assignment", "tomorrow is submission",
    ]
    if any(ws in clean_lower for ws in work_signals):
        explicit_media_request = any(
            re.search(r"\b" + re.escape(sig) + r"\b", clean_lower)
            for sig in ["suggest songs", "recommend songs", "play music", "listen to spotify", "recommend music"]
        )
        if not explicit_media_request:
            return None

    # 2b. Handle Exam / Study Intent: Provide relevant study resources via Tavily / YouTube, no Spotify tracks
    exam_keywords = ["internal exam", "semester exam", "midterm", "finals", "exam preparation"]
    if any(re.search(r"\b" + re.escape(ek) + r"\b", clean_lower) for ek in exam_keywords) or (
        "exam" in clean_lower and not any(kw in clean_lower for kw in ["song", "music", "movie", "cricket"])
    ):
        return {
            "has_intent": True,
            "category": "study",
            "query": f"{clean} study resources",
            "preferred_providers": ["tavily", "youtube"],
        }

    # 2c. Handle website / links / shopping / learning / booking / images intent (e.g. "give me a bangles
    # website", "give cricket websites", "give apple iphone website", "find websites to learn Java", "samsung laptop buying links",
    # "give some virat kholi images link", "official website for NVIDIA", "book train tickets").
    # Checked before the music/general-recommendation rules below, because a request like "suggest a website for bangles"
    # would otherwise be swallowed by the generic "recommend/suggest" fallback and default to unrelated Spotify/YouTube results.
    has_website_word = bool(re.search(r"\bweb\s?sites?\b|\bweb\s?pages?\b", clean_lower))
    has_official_word = bool(re.search(r"\bofficial\b", clean_lower))
    has_site_word = bool(re.search(r"\bsites?\b", clean_lower))
    has_link_word = bool(re.search(r"\blinks?\b|\burls?\b", clean_lower))
    has_image_word = bool(re.search(r"\bimages?\b|\bphotos?\b|\bpics?\b|\bpictures?\b", clean_lower))

    shopping_verbs = ["buy", "buying", "shop", "shopping", "purchase", "purchasing", "order", "ordering"]
    has_shopping_word = any(re.search(r"\b" + re.escape(v) + r"\b", clean_lower) for v in shopping_verbs)
    booking_verbs = ["book", "booking", "reserve", "reserving", "reservation", "reservations"]
    has_booking_word = any(re.search(r"\b" + re.escape(v) + r"\b", clean_lower) for v in booking_verbs)
    learning_words = ["learn", "learning", "tutorial", "tutorials", "course", "courses", "practice", "docs", "documentation"]
    has_learning_word = any(re.search(r"\b" + re.escape(v) + r"\b", clean_lower) for v in learning_words)
    tool_words = ["resume", "cv builder", "create a resume", "coding practice"]
    has_tool_word = any(w in clean_lower for w in tool_words)

    is_official_site_request = has_official_word and (has_website_word or has_site_word or has_link_word)
    is_website_or_link_request = has_website_word or has_link_word or is_official_site_request

    if is_website_or_link_request or has_shopping_word or has_booking_word or (has_learning_word and (has_website_word or has_link_word)) or has_image_word:
        q = clean
        # Strip generic request scaffolding regardless of exact phrasing
        q = re.sub(REQUEST_PREFIXES, "", q, flags=re.I).strip()
        q = re.sub(
            r"^(?:give|show|find|get|send|share|suggest|recommend|list|tell)\s+(?:me|us)?\s*(?:\bsome\b|\ba\s+few\b|\ba\s+couple\s+of\b|\ba\b|\ban\b|\bthe\b|\bfew\b)?\s*",
            "", q, flags=re.I,
        ).strip()
        q = re.sub(r"[?!.,]+$", "", q).strip()
        q = re.sub(r"\b(?:here\s*now|here|now|please)\b", "", q, flags=re.I).strip()
        q = re.sub(r"\b(?:web\s?sites?|web\s?pages?|official\s+sites?|links?|urls?)\b", "", q, flags=re.I).strip()
        if has_image_word:
            q = re.sub(r"\b(?:images?|photos?|pics?|pictures?)\b", "", q, flags=re.I).strip()
        q = re.sub(r"\bfor\s+me\b", "", q, flags=re.I).strip()
        q = re.sub(r"^(?:to\b|for\b|\ba\b|\bthe\b|\bsome\b|\ban\b|\babout\b|\bof\b|\s+)+", "", q, flags=re.I).strip()
        q = re.sub(r"\s+", " ", q).strip()

        # If nothing but filler words is left, recover context if available
        generic_leftover = {"", "some", "good", "any", "a", "few", "more", "other", "other options"}
        if q.lower().strip() in generic_leftover and recent_context:
            combined_context = " ".join(
                (m.content if hasattr(m, "content") else (m.get("content", "") if isinstance(m, dict) else str(m)))
                for m in recent_context
            ).lower()
            ctx_topic = re.sub(
                r"\b(?:websites?|web\s*sites?|web\s*pages?|links?|urls?|images?|buy|shop|shopping|online|official|book|booking|give|show|find|get|send|share|suggest|recommend|me|us|some|a|an|the|please|can|you|could)\b",
                "", combined_context, flags=re.I,
            ).strip()
            ctx_topic = re.sub(r"\s+", " ", ctx_topic).strip()
            if ctx_topic:
                q = ctx_topic

        if q.lower().strip() in generic_leftover:
            return None

        # Query augmentation is intent-specific:
        if is_official_site_request:
            category = "official_website"
            q_clean = re.sub(r"\bofficial\b", "", q, flags=re.I).strip() or q
            search_query = f"{q_clean} official website"
        elif has_booking_word:
            category = "website"
            search_query = f"{q} online booking website"
        elif has_image_word:
            category = "images"
            search_query = f"{q} images"
        elif has_learning_word or has_tool_word:
            category = "website"
            search_query = f"{q} best websites resources tutorials"
        elif has_shopping_word:
            category = "shopping"
            search_query = f"{q} online store shopping"
        else:
            category = "website"
            search_query = f"{q} website"

        return {
            "has_intent": True,
            "category": category,
            "query": search_query,
            "preferred_providers": ["tavily"],
            "entity": q,
        }

    # 3. Handle explicit ambiguous actor case: e.g. 'I like actor Vijay'
    # If an actor is mentioned without media request (movies, songs, trailers), do NOT assume music!
    actor_pattern = r"\bactor\s+([a-zA-Z0-9_\s]+)"
    actor_match = re.search(actor_pattern, clean_lower)
    if actor_match and not any(kw in clean_lower for kw in ["movie", "movies", "trailer", "film", "song", "songs", "music"]):
        return None

    # 4. Handle Cricket Domain early to prevent false positives in continuation
    cricket_keywords = ["cricket", "ipl", "world cup", "match score", "cricket score", "test match", "t20", "scorecard"]
    if any(kw in clean_lower for kw in cricket_keywords):
        return {
            "has_intent": True,
            "category": "cricket",
            "query": clean,
            "preferred_providers": ["tavily", "youtube"],
        }

    # 5. Handle Movies / Cinema Intent (e.g. 'Vijay movies', 'Vijay movie trailer')
    movie_keywords = ["movies", "movie trailer", "film trailer", "teaser", "cinema trailer", "movie"]
    if any(re.search(r"\b" + re.escape(kw) + r"\b", clean_lower) for kw in movie_keywords):
        if re.search(r"\b[a-zA-Z0-9_-]+\s+(?:movies?|films?|trailers?)\b", clean, flags=re.I):
            q = re.sub(r"^(?:i like|i love|watch|show me|recommend|suggest)\s+", "", clean, flags=re.I).strip()
            q = re.sub(r"[?!.,]+$", "", q).strip()
        else:
            q = re.sub(REQUEST_PREFIXES, "", clean, flags=re.I).strip()
            q = re.sub(r"[?!.,]+$", "", q).strip()
            q = re.sub(r"\b(?:for\s+me|to\s+watch|trailer|teaser|film|movie|movies|recommendations?|suggestions?)\b", "", q, flags=re.I).strip()
            q = re.sub(r"^(?:a\s+|some\s+|good\s+|popular\s+|latest\s+|new\s+)+", "", q, flags=re.I).strip()
            if not q or len(q) < 2:
                q = "popular movies"
        return {
            "has_intent": True,
            "category": "movie",
            "query": q,
            "preferred_providers": ["youtube", "tavily"],
        }

    # 5b. Follow-up song reference: "Send me that song", "Share that song", "Which song is that"
    follow_up_song = re.search(r"\b(?:send|share|link|play|give)\s+(?:me\s+)?(?:that|the)\s+song\b|\b(?:what|which)\s+(?:is\s+)?(?:that|the)\s+song\b", clean_lower)
    if follow_up_song and recent_context:
        combined_context = " ".join(
            (m.content if hasattr(m, "content") else (m.get("content", "") if isinstance(m, dict) else str(m)))
            for m in recent_context
        ).lower()
        if "anirudh" in combined_context:
            return {
                "has_intent": True,
                "category": "music",
                "query": "latest Anirudh song",
                "preferred_providers": ["spotify", "youtube"],
            }
        m_ctx = re.search(r"\b([a-zA-Z0-9_\s]+?)\s+song\b", combined_context)
        if m_ctx:
            ctx_entity = m_ctx.group(1).strip()
            if ctx_entity and ctx_entity not in {"that", "the", "a", "this"}:
                return {
                    "has_intent": True,
                    "category": "music",
                    "query": f"{ctx_entity} song",
                    "preferred_providers": ["spotify", "youtube"],
                }

    # 6. Handle Music / Spotify Intent
    music_keywords = ["spotify", "song", "songs", "track", "tracks", "music", "singer", "artist", "album", "listen to", "playlist", "melody", "audio"]
    if any(re.search(r"\b" + re.escape(kw) + r"\b", clean_lower) for kw in music_keywords):
        wants_spotify = "spotify" in clean_lower or any(kw in clean_lower for kw in ["song", "songs", "track", "tracks", "album", "music", "melody"])
        preferred = ["spotify", "youtube"] if wants_spotify else ["youtube", "spotify"]

        q = clean
        q = re.sub(r"\b(on|via|from)\s+spotify\??", "", q, flags=re.I).strip()
        q = re.sub(REQUEST_PREFIXES, "", q, flags=re.I).strip()
        q = re.sub(r"[?!.,]+$", "", q).strip()
        q = re.sub(r"\bfor\s+me\b", "", q, flags=re.I).strip()

        # Check for context modifier like "for travelling", "for gym", "for study"
        context_mod_match = re.search(r"\b(?:for|while|when)\s+(?:travelling|traveling|travel|driving|drive|working out|gym|relaxing|study|party)\b", clean_lower)
        context_mod = context_mod_match.group(0) if context_mod_match else ""

        # Check for 'have you heard the latest [Artist] song'
        m_heard = re.search(r"(?:have\s+you\s+heard|heard)\s+(?:the\s+)?(?:latest|new)?\s*([a-zA-Z0-9_\s]+?)\s+song", clean_lower)
        if m_heard and m_heard.group(1).strip():
            artist_name = m_heard.group(1).strip()
            artist_name = re.sub(r"^(?:bro|buddy|dude|hey)\s*,?\s*", "", artist_name).strip()
            q = f"latest {artist_name} song".strip()
        else:
            # If pattern is '[Entity] songs' or '[Entity] music' -> extract entity
            m = re.search(r"^(.*?)\s+(?:songs?|music|tracks?|playlist|album)\b", q, flags=re.I)
            if m and m.group(1).strip():
                extracted = m.group(1).strip()
                extracted = re.sub(REQUEST_PREFIXES, "", extracted, flags=re.I).strip()
                extracted = re.sub(r"^(?:bro|buddy|dude|hey)\s*,?\s*", "", extracted, flags=re.I).strip()
                if extracted.lower() in {"", "some", "good", "new", "latest", "best", "any", "some good", "top"}:
                    q = f"Trending songs {context_mod}".strip()
                elif extracted.lower() in {"tamil", "hindi", "english", "telugu", "malayalam", "punjabi", "rock", "pop", "jazz"}:
                    q = f"{extracted} songs {context_mod}".strip()
                else:
                    q = f"{extracted} {context_mod}".strip() if context_mod else extracted

        if not q or q.lower() in {"song", "songs", "some songs", "music", "some music", "tracks", "playlist", "album", "spotify", "audio", "melody", "some good", "song recommendations", "music recommendations"}:
            q = f"Trending songs {context_mod}".strip() if context_mod else "Trending songs"

        # Ensure query is not a conversational/meta sentence
        meta_verbs = {"talk", "type", "tell", "said", "ask", "changes", "think", "know", "monitor", "mistakes", "fix", "when", "only", "other"}
        query_words = set(re.findall(r"\b[a-zA-Z]+\b", q.lower()))
        if len(query_words.intersection(meta_verbs)) >= 2 or len(q.split()) > 7:
            return None

        return {
            "has_intent": True,
            "category": "music",
            "query": q,
            "preferred_providers": preferred,
        }

    # 6b. Short continuation requests ("more options", "show me more", "anything else?") reuse
    # the most recent topic from context instead of defaulting to music.
    continuation_phrase = re.search(
        r"^(?:more|more options?|show more|anything else|any other options?|give me more|more like this)[!.?]*$",
        clean_lower,
    )
    if continuation_phrase and recent_context:
        combined_context = " ".join(
            (m.content if hasattr(m, "content") else (m.get("content", "") if isinstance(m, dict) else str(m)))
            for m in recent_context
        ).lower()
        if re.search(r"\bweb\s?sites?\b|\bweb\s?pages?\b|\bofficial\b|\bbuy\b|\bshop\b|\bshopping\b|\bbook\b|\bbooking\b", combined_context):
            topic = re.sub(r"\b(?:websites?|web\s*sites?|buy|shop|shopping|online|official|book|booking)\b", "", combined_context, flags=re.I).strip()
            topic = re.sub(r"\s+", " ", topic) or combined_context
            return {
                "has_intent": True,
                "category": "shopping",
                "query": f"{topic} online store shopping",
                "preferred_providers": ["tavily"],
            }
        if any(re.search(r"\b" + re.escape(kw) + r"\b", combined_context) for kw in music_keywords):
            return {"has_intent": True, "category": "music", "query": "more trending songs", "preferred_providers": ["spotify", "youtube"]}
        if any(term in combined_context for term in ["movie", "film", "trailer", "cinema"]):
            return {"has_intent": True, "category": "movie", "query": "popular movies", "preferred_providers": ["youtube", "tavily"]}
        if any(kw in combined_context for kw in cricket_keywords):
            return {"has_intent": True, "category": "cricket", "query": "cricket scores", "preferred_providers": ["tavily", "youtube"]}

    # 7. General recommendation triggers without explicit domain
    general_rec = re.search(r"\b(?:recommend|recomend|suggest)(?:ations?|ing|ed|something)?\b|\bany\s+recommendations?\b|\bwhat\s+do\s+you\s+recommend\b", clean_lower)
    if general_rec:
        combined = ""
        if recent_context:
            combined = " ".join(
                (m.content if hasattr(m, "content") else str(m)) for m in recent_context
            ).lower()
        if any(term in combined for term in ["movie", "film", "trailer", "cinema"]):
            return {"has_intent": True, "category": "movie", "query": "popular movies", "preferred_providers": ["youtube", "tavily"]}
        else:
            return {"has_intent": True, "category": "music", "query": "Trending songs", "preferred_providers": ["spotify", "youtube"]}

    # 8. Continuation from context: e.g. User types 'I like Hukum and...'
    # when recent context asked about favorite song / artist music
    if recent_context:
        combined_context = " ".join(
            (m.content if hasattr(m, "content") else str(m)) for m in recent_context
        ).lower()
        if any(term in combined_context for term in ["song", "music", "spotify", "anirudh", "artist", "singer", "which song"]):
            m_song = re.search(
                r"^(?:i like|my favorite is|love|listen to)\s+([a-zA-Z0-9\s]{2,25})$",
                re.sub(r"(\s+and|\.{2,})+$", "", clean, flags=re.I).strip(),
                flags=re.I,
            )
            if m_song:
                clean_stripped = re.sub(r"^(i like|i love|my favorite is|listen to)\s+", "", clean, flags=re.I)
                clean_song = re.sub(r"(\s+and|\.{2,})+$", "", clean_stripped, flags=re.I).strip()
                if clean_song and clean_song.lower() not in {"this", "that", "it", "yes", "no"}:
                    artist = "Anirudh" if "anirudh" in combined_context else ""
                    query = f"{clean_song} {artist}".strip()
                    return {
                        "has_intent": True,
                        "category": "music",
                        "query": query,
                        "preferred_providers": ["spotify", "youtube"],
                    }

    return None


def extract_fast_recommendation_intent(text: str) -> Optional[Dict[str, Any]]:
    """Legacy compatibility wrapper for fast intent detection."""
    return extract_contextual_draft_intent(text)


class RecommendationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ai_repo = AiRepository(session)
        self.conv_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)
        self.conv_service = ConversationService(session)

    _RELEVANCE_STOPWORDS = {
        "the", "a", "an", "to", "for", "of", "on", "in", "and", "or", "me", "give", "find",
        "website", "websites", "web", "site", "sites", "page", "pages", "buy", "online",
        "official", "best", "resources", "tutorials", "booking", "book", "shop", "shopping",
        "link", "links", "store", "stores", "images", "image", "photos", "photo", "pics", "pic",
    }

    @classmethod
    def _rank_website_results(
        cls, results: List[Dict[str, Any]], query: str, official: bool = False, entity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Rank Tavily results against the actual request, and -- when the request names a real
        subject (e.g. "bangles", "java", "nvidia") -- drop results that don't mention it at all,
        so a leftover/unrelated page from a previous topic is never shown as if it matched this
        one. `entity` is the cleaned subject phrase (post filler-word stripping); falls back to
        the full query if not given. If keyword-matching would remove every result (the subject
        terms are unusually phrased and Tavily's own relevance is all we have), nothing is
        dropped -- only reordered -- so a genuinely good result is never discarded outright."""
        source_text = entity if entity else query
        terms = {
            t for t in re.findall(r"[a-z0-9]+", source_text.lower()) if t not in cls._RELEVANCE_STOPWORDS and len(t) > 2
        }

        def keyword_hits(item: Dict[str, Any]) -> int:
            haystack = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('url', '')}".lower()
            return sum(1 for t in terms if t in haystack)

        def domain_hit(item: Dict[str, Any]) -> bool:
            domain = re.sub(r"^https?://(www\.)?", "", item.get("url", "").lower()).split("/")[0]
            return official and any(t in domain for t in terms)

        def provider_score(item: Dict[str, Any]) -> float:
            return float((item.get("extra_data") or {}).get("relevance_score") or 0.0)

        def score(item: Dict[str, Any]) -> tuple:
            return (domain_hit(item), keyword_hits(item), provider_score(item))

        ranked = sorted(results, key=score, reverse=True)

        # Exact-keyword enforcement: when we know what the user actually asked for, a result
        # that mentions none of those words is almost certainly off-topic (e.g. carried over
        # from an earlier, different search) and should not be shown as if it matched.
        if terms:
            on_topic = [r for r in ranked if keyword_hits(r) > 0 or domain_hit(r)]
            if on_topic:
                return on_topic

        return ranked

    async def _fetch_provider_results(
        self,
        category: str,
        query: str,
        preferred_providers: Optional[List[str]] = None,
        entity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Check cache first (<1ms return)
        cache_key = f"{category}:{query.strip().lower()}:{','.join(preferred_providers or [])}"
        cached = _recommendations_cache.get(cache_key)
        if cached and (time.time() - cached[0] < 60.0):
            return cached[1]

        raw_results: List[Dict[str, Any]] = []

        # 1. Music domain
        if category == "music":
            providers_order = preferred_providers or ["spotify", "youtube"]
            if providers_order and providers_order[0] == "spotify":
                if settings.is_provider_configured("spotify"):
                    try:
                        clean_query = re.sub(r"\bspotify\b", "", query, flags=re.I).strip() or query
                        sp_items = await spotify_provider.search_tracks(query=clean_query, limit=3)
                        raw_results.extend(sp_items)
                    except Exception as e:
                        logger.warning(f"Spotify search error: {e}")

                if settings.is_provider_configured("youtube"):
                    try:
                        yt_items = await youtube_provider.search_videos(query=query, limit=2)
                        raw_results.extend(yt_items)
                    except Exception as e:
                        logger.warning(f"YouTube search error: {e}")
            else:
                if settings.is_provider_configured("youtube"):
                    try:
                        yt_items = await youtube_provider.search_videos(query=query, limit=3)
                        raw_results.extend(yt_items)
                    except Exception as e:
                        logger.warning(f"YouTube search error: {e}")

                if settings.is_provider_configured("spotify"):
                    try:
                        clean_query = re.sub(r"\bspotify\b", "", query, flags=re.I).strip() or query
                        sp_items = await spotify_provider.search_tracks(query=clean_query, limit=3)
                        raw_results.extend(sp_items)
                    except Exception as e:
                        logger.warning(f"Spotify search error: {e}")

        # 2. Cricket domain
        elif category == "cricket":
            if settings.is_provider_configured("tavily"):
                try:
                    tv_items = await tavily_provider.search(query=f"{query} cricket score match", limit=3, category="cricket")
                    raw_results.extend(tv_items)
                except Exception as e:
                    logger.warning(f"Tavily cricket search error: {e}")

            if settings.is_provider_configured("youtube"):
                try:
                    yt_cricket = await youtube_provider.search_videos(query=f"{query} highlights", limit=2)
                    for item in yt_cricket:
                        item["category"] = "cricket"
                    raw_results.extend(yt_cricket)
                except Exception as e:
                    logger.warning(f"YouTube cricket search error: {e}")

        # 3. Movies / Media
        elif category == "movie":
            if settings.is_provider_configured("youtube"):
                try:
                    yt_movie = await youtube_provider.search_videos(query=f"{query} trailer", limit=2)
                    for item in yt_movie:
                        item["category"] = "movie"
                    raw_results.extend(yt_movie)
                except Exception as e:
                    logger.warning(f"YouTube movie trailer error: {e}")

            if settings.is_provider_configured("tavily"):
                try:
                    tv_movie = await tavily_provider.search(query=f"{query} movie review details", limit=2, category="movie")
                    raw_results.extend(tv_movie)
                except Exception as e:
                    logger.warning(f"Tavily movie search error: {e}")

        # 4. Places / Travel
        elif category == "place":
            if settings.is_provider_configured("tavily"):
                try:
                    tv_place = await tavily_provider.search(query=f"{query} best places to visit travel", limit=3, category="place")
                    raw_results.extend(tv_place)
                except Exception as e:
                    logger.warning(f"Tavily place search error: {e}")

            if settings.is_provider_configured("youtube"):
                try:
                    yt_place = await youtube_provider.search_videos(query=f"{query} travel guide", limit=2)
                    for item in yt_place:
                        item["category"] = "place"
                    raw_results.extend(yt_place)
                except Exception as e:
                    logger.warning(f"YouTube travel search error: {e}")

        # 5. Website / shopping / official-site / image requests: Tavily only. These must never
        # silently fall back to YouTube or Spotify -- a failed web search should surface as
        # "no results", not as an unrelated video or song.
        elif category in ("website", "shopping", "official_website", "images"):
            if settings.is_provider_configured("tavily"):
                try:
                    tv_items = await tavily_provider.search(query=query, limit=6, category=category)
                    ranked = self._rank_website_results(tv_items, query=query, official=(category == "official_website"), entity=entity)
                    raw_results.extend(ranked[:4])
                except Exception as e:
                    logger.warning(f"Tavily website search error: {e}")

        # 6. General Web / Default (study, news, generic "web" category from the AI fallback)
        else:
            if settings.is_provider_configured("tavily"):
                try:
                    tv_items = await tavily_provider.search(query=query, limit=3, category=category)
                    raw_results.extend(tv_items)
                except Exception as e:
                    logger.warning(f"Tavily search error: {e}")

            if settings.is_provider_configured("youtube") and not raw_results:
                try:
                    yt_items = await youtube_provider.search_videos(query=query, limit=2)
                    raw_results.extend(yt_items)
                except Exception as e:
                    logger.warning(f"YouTube search error: {e}")

        if raw_results:
            _recommendations_cache[cache_key] = (time.time(), raw_results)

        return raw_results

    async def evaluate_and_fetch_recommendations(
        self,
        conversation_id: uuid.UUID,
        triggering_message_id: Optional[uuid.UUID] = None,
    ) -> List[RecommendationItemResponse]:
        """
        Detect search intent and retrieve verified external results.
        Uses fast intent extraction for immediate response and Nemotron for contextual cues.
        """
        if not settings.RECOMMENDATIONS_ENABLED:
            return []

        now = time.time()
        last_time = _last_recommendation_time.get(conversation_id, 0.0)
        # 3 second debounce per conversation
        if now - last_time < 3.0:
            return []

        messages = await self.message_repo.get_recent_messages(
            conversation_id=conversation_id,
            limit=10,
        )
        if not messages:
            return []

        # 1. Fast heuristic intent detection from latest message
        latest_msg = messages[-1] if messages else None
        if not latest_msg:
            return []

        intent = extract_contextual_draft_intent(latest_msg.content, recent_context=messages[:-1])

        # If fast intent did not match, check if the latest message is a work/deadline or chitchat message
        # In that case, do NOT fall back to LLM historical search!
        latest_lower = latest_msg.content.lower().strip()
        work_signals = ["deadline", "project", "submission", "submitting", "sprint", "meeting", "deliverable", "budget"]
        if not intent and any(ws in latest_lower for ws in work_signals):
            return []
        if not intent and latest_lower in {"hi", "hello", "hey", "ok", "okay", "thanks", "sure", "cool", "yes", "no", "bye"}:
            return []

        # 2. Contextual LLM detection fallback if fast intent did not match and not suppressed
        if not intent and (settings.is_provider_configured("nvidia") or settings.is_provider_configured("groq") or settings.is_provider_configured("nebius")):
            context = [
                {
                    "id": str(m.id),
                    "sender_username": m.sender.username if m.sender else "User",
                    "content": m.content,
                }
                for m in messages
            ]
            try:
                intent = await ai_router.detect_recommendation_intent(context)
            except Exception as exc:
                logger.warning(f"AI recommendation intent detection failed: {exc}")
                return []

        if not intent or not intent.get("has_intent"):
            return []

        query = intent.get("query", "").strip()
        category = intent.get("category", "web")
        preferred_providers = intent.get("preferred_providers")
        entity = intent.get("entity")
        if not query:
            return []

        try:
            raw_results = await self._fetch_provider_results(
                category=category,
                query=query,
                preferred_providers=preferred_providers,
                entity=entity,
            )
            if not raw_results:
                return []

            # Deduplicate against existing recommendations in the conversation
            existing = await self.ai_repo.get_recommendations_by_conversation(conversation_id, limit=100)
            seen_urls = {item.url.strip() for item in existing if item.url}
            persisted_responses: List[RecommendationItemResponse] = []

            for r in raw_results:
                url = r.get("url", "").strip()
                if not (url.startswith("http://") or url.startswith("https://")):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                item = await self.ai_repo.create_recommendation(
                    conversation_id=conversation_id,
                    source=r["source"],
                    title=r["title"],
                    url=url,
                    snippet=r.get("snippet"),
                    category=r.get("category", category),
                    published_date=r.get("published_date"),
                    extra_data=r.get("extra_data"),
                    triggered_by_message_id=triggering_message_id,
                )
                persisted_responses.append(RecommendationItemResponse.model_validate(item))

            if persisted_responses:
                _last_recommendation_time[conversation_id] = now

            return persisted_responses

        except Exception as exc:
            logger.error(f"Recommendation evaluation error: {exc}")
            return []

    async def request_recommendations(
        self,
        conversation_id: uuid.UUID,
        current_user_id: uuid.UUID,
        query: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[RecommendationItemResponse]:
        """
        Explicitly request contextual recommendations for a conversation.
        Bypasses cooldown so user requests are served immediately.
        """
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        if not query or not query.strip():
            messages = await self.message_repo.get_recent_messages(
                conversation_id=conversation_id,
                limit=10,
            )
            if not messages:
                return []
            context = [
                {
                    "id": str(m.id),
                    "sender_username": m.sender.username if m.sender else "User",
                    "content": m.content,
                }
                for m in messages
            ]
            intent = await ai_router.detect_recommendation_intent(context)
            if not intent or not intent.get("has_intent"):
                return []
            query = intent.get("query", "").strip()
            category = intent.get("category", "web")

        query = query.strip()
        if not query:
            return []

        category = category or "web"
        raw_results = await self._fetch_provider_results(category, query)
        if not raw_results:
            return []

        existing = await self.ai_repo.get_recommendations_by_conversation(conversation_id, limit=100)
        seen_urls = {item.url.strip() for item in existing if item.url}
        persisted_responses: List[RecommendationItemResponse] = []
        # Anchor to the current point in the conversation so the item is listed as recent.
        last_message = await self.message_repo.get_last_message(conversation_id)

        for r in raw_results:
            url = r.get("url", "").strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            item = await self.ai_repo.create_recommendation(
                conversation_id=conversation_id,
                source=r["source"],
                title=r["title"],
                url=url,
                snippet=r.get("snippet"),
                category=r.get("category", category),
                published_date=r.get("published_date"),
                extra_data=r.get("extra_data"),
                triggered_by_message_id=last_message.id if last_message else None,
            )
            persisted_responses.append(RecommendationItemResponse.model_validate(item))

        return persisted_responses

    async def share_recommendation_in_chat(
        self,
        conversation_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> MessageRead:
        """
        Explicitly shares a recommendation item as a normal chat message.
        Never shared automatically without explicit user action.
        """
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        item = await self.ai_repo.get_recommendation_by_id(recommendation_id)
        if not item or item.conversation_id != conversation_id:
            raise NotFoundError("Recommendation item not found in this conversation.")

        # Persist as link_share chat message
        content = f"Shared: {item.title}\n{item.url}"
        msg_in = MessageCreate(
            content=content,
            message_type="link_share",
            msg_metadata={
                "source": item.source,
                "recommendation_id": str(item.id),
                "title": item.title,
                "url": item.url,
                "extra_data": item.extra_data,
            },
        )

        message = await self.conv_service.save_message(
            conversation_id=conversation_id,
            sender_id=current_user_id,
            message_in=msg_in,
        )

        await self.ai_repo.mark_recommendation_shared(item)
        return message

    async def get_conversation_recommendations(
        self,
        conversation_id: uuid.UUID,
        current_user_id: uuid.UUID,
        limit: int = 50,
        include_dismissed: bool = False,
    ) -> List[RecommendationItemResponse]:
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        recent_messages = await self.message_repo.get_recent_messages(conversation_id, limit=5)
        recent_text = " ".join([m.content.lower() for m in recent_messages]) if recent_messages else ""
        has_work_topic = any(ws in recent_text for ws in ["deadline", "project", "submission", "sprint", "meeting", "deliverable"])

        items = await self.ai_repo.get_recommendations_by_conversation(
            conversation_id,
            limit=min(limit, RECENT_RECOMMENDATION_LIMIT),
            include_dismissed=include_dismissed,
            recent_message_window=RECENT_MESSAGE_WINDOW,
        )

        filtered_items = []
        latest_ids = {str(m.id) for m in recent_messages[-3:]} if recent_messages else set()
        for item in items:
            # Shared items remain in the chat
            if item.is_shared_in_chat:
                filtered_items.append(item)
                continue
            # If the chat has moved on to work/deadline, suppress unshared music/video cards
            if has_work_topic and item.category in {"music", "video", "movie"}:
                continue
            # Only keep unshared cards if triggered by one of the latest 3 messages
            if item.triggered_by_message_id and str(item.triggered_by_message_id) in latest_ids:
                filtered_items.append(item)

        return [RecommendationItemResponse.model_validate(item) for item in filtered_items]

    async def dismiss_recommendation(
        self,
        conversation_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> RecommendationItemResponse:
        """Mark a recommendation item as dismissed by a conversation participant."""
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        item = await self.ai_repo.get_recommendation_by_id(recommendation_id)
        if not item or item.conversation_id != conversation_id:
            raise NotFoundError("Recommendation item not found in this conversation.")

        dismissed = await self.ai_repo.dismiss_recommendation(item, current_user_id)
        return RecommendationItemResponse.model_validate(dismissed)

    async def evaluate_draft_recommendations(
        self,
        conversation_id: uuid.UUID,
        draft: str,
        current_user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Evaluate recommendations for an active draft message in the composer.
        Uses fast contextual intent detection, searches providers (Spotify, YouTube, etc.),
        and returns compact recommendation items without requiring the message to be sent first.
        """
        is_member = await self.conv_repo.is_member(conversation_id, current_user_id)
        if not is_member:
            raise ForbiddenError("You are not a member of this conversation.")

        if not settings.RECOMMENDATIONS_ENABLED:
            return {"has_intent": False, "recommendations": []}

        # 1. Fetch recent messages for conversational context
        messages = await self.message_repo.get_recent_messages(
            conversation_id=conversation_id,
            limit=6,
        )

        # 2. Fast contextual intent extraction
        intent = extract_contextual_draft_intent(draft, messages)
        if not intent or not intent.get("has_intent"):
            return {"has_intent": False, "recommendations": []}

        query = intent.get("query", "").strip()
        category = intent.get("category", "web")
        preferred_providers = intent.get("preferred_providers")
        entity = intent.get("entity")
        if not query:
            return {"has_intent": False, "recommendations": []}

        # 3. Provider search (with cache)
        raw_results = await self._fetch_provider_results(
            category=category,
            query=query,
            entity=entity,
            preferred_providers=preferred_providers,
        )
        if not raw_results:
            result = {
                "has_intent": True,
                "category": category,
                "query": query,
                "recommendations": [],
            }
            # Distinguish "the provider isn't configured" from "no relevant results" so the UI
            # can say so, instead of silently looking the same as an empty/irrelevant result set.
            if category in ("website", "shopping", "official_website") and not settings.is_provider_configured("tavily"):
                result["provider_unavailable"] = "tavily"
            return result

        # 4. Check existing recommendations in conversation to reuse or persist
        existing = await self.ai_repo.get_recommendations_by_conversation(conversation_id, limit=50)
        seen_urls = {item.url.strip() for item in existing if item.url}
        persisted_responses: List[RecommendationItemResponse] = []

        for r in raw_results[:3]:  # Top 3 results for composer dock
            url = r.get("url", "").strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                continue

            matched = next((item for item in existing if item.url == url), None)
            if matched:
                persisted_responses.append(RecommendationItemResponse.model_validate(matched))
                continue

            if url in seen_urls:
                continue
            seen_urls.add(url)

            item = await self.ai_repo.create_recommendation(
                conversation_id=conversation_id,
                source=r["source"],
                title=r["title"],
                url=url,
                snippet=r.get("snippet"),
                category=r.get("category", category),
                published_date=r.get("published_date"),
                extra_data=r.get("extra_data"),
                triggered_by_message_id=None,
            )
            persisted_responses.append(RecommendationItemResponse.model_validate(item))

        await self.session.commit()

        return {
            "has_intent": True,
            "category": category,
            "query": query,
            "recommendations": persisted_responses,
        }

