from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings, settings
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.recommendation import RecommendationItem
from app.models.user import User
from app.providers.nvidia_provider import nvidia_provider
from app.providers.spotify_provider import spotify_provider
from app.providers.tavily_provider import tavily_provider
from app.providers.youtube_provider import youtube_provider
from app.services.recommendation_service import RecommendationService, _last_recommendation_time


@pytest.mark.asyncio
async def test_recommendations_retrieval_and_url_validation(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    _last_recommendation_time.clear()

    # 1. Setup conversation and membership
    conv = Conversation(is_group=True, title="Tamil Cinema & Music", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))
    await db_session.commit()

    msg = Message(conversation_id=conv.id, sender_id=test_user.id, content="Did anyone listen to the new Anirudh Tamil song?")
    db_session.add(msg)
    await db_session.commit()

    mock_intent = {
        "has_intent": True,
        "category": "music",
        "query": "Anirudh new Tamil song",
        "preferred_providers": ["youtube", "spotify"],
    }

    mock_youtube_items = [
        {
            "source": "youtube",
            "title": "Hukum - Thalaivar Alappara (Lyric Video)",
            "url": "https://www.youtube.com/watch?v=12345",
            "snippet": "Jailer soundtrack by Anirudh Ravichander",
            "category": "music",
            "published_date": "2023-07-17",
            "extra_data": {"video_id": "12345"},
        },
        {
            # Invalid URL scheme - must be filtered out
            "source": "youtube",
            "title": "Malicious Script Link",
            "url": "javascript:alert(1)",
            "snippet": "exploit",
            "category": "music",
        },
    ]

    mock_spotify_items = [
        {
            "source": "spotify",
            "title": "Naa Ready - Leo",
            "url": "https://open.spotify.com/track/67890",
            "snippet": "Track by Thalapathy Vijay, Anirudh",
            "category": "music",
            "published_date": "2023-06-22",
            "extra_data": {"track_id": "67890"},
        }
    ]

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_recommendation_intent", return_value=mock_intent), \
         patch.object(youtube_provider, "_ensure_configured", return_value=None), \
         patch.object(youtube_provider, "search_videos", return_value=mock_youtube_items), \
         patch.object(spotify_provider, "_ensure_configured", return_value=None), \
         patch.object(spotify_provider, "search_tracks", return_value=mock_spotify_items):

        rec_service = RecommendationService(db_session)
        items = await rec_service.evaluate_and_fetch_recommendations(conv.id, triggering_message_id=msg.id)

        assert len(items) == 2  # JavaScript link was rejected
        urls = [i.url for i in items]
        assert "https://www.youtube.com/watch?v=12345" in urls
        assert "https://open.spotify.com/track/67890" in urls


@pytest.mark.asyncio
async def test_share_recommendation_as_normal_chat_message(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    # Setup conversation and membership
    conv = Conversation(is_group=True, title="Cricket Fans", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))
    await db_session.commit()

    # Seed a persisted recommendation item
    rec = RecommendationItem(
        conversation_id=conv.id,
        source="tavily",
        title="India vs Australia World Cup Highlights",
        url="https://sportsnews.com/ind-vs-aus",
        snippet="Key moments and statistics from the cricket match.",
        category="cricket",
        extra_data={"score": "240/10"},
    )
    db_session.add(rec)
    await db_session.commit()
    await db_session.refresh(rec)

    # User clicks Share in Chat
    share_resp = await client.post(
        f"/api/v1/conversations/{conv.id}/recommendations/{rec.id}/share",
        headers=auth_headers,
    )
    assert share_resp.status_code == 201
    msg_data = share_resp.json()
    assert msg_data["message_type"] == "link_share"
    assert "India vs Australia" in msg_data["content"]
    assert msg_data["msg_metadata"]["url"] == "https://sportsnews.com/ind-vs-aus"
    assert msg_data["sender_username"] == test_user.username


@pytest.mark.asyncio
async def test_duplicate_recommendation_suppression(
    db_session: AsyncSession, test_user: User
):
    _last_recommendation_time.clear()

    conv = Conversation(is_group=True, title="Music Club", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()

    # Pre-existing recommendation already in DB
    existing_rec = RecommendationItem(
        conversation_id=conv.id,
        source="spotify",
        title="Pookkal Pookkum",
        url="https://open.spotify.com/track/pookkal",
        category="music",
    )
    db_session.add(existing_rec)

    msg = Message(conversation_id=conv.id, sender_id=test_user.id, content="Suggest some good Tamil songs")
    db_session.add(msg)
    await db_session.commit()

    mock_intent = {
        "has_intent": True,
        "category": "music",
        "query": "Tamil melody songs",
        "preferred_providers": ["spotify"],
    }

    # Provider returns the existing track AND a new track
    mock_spotify_items = [
        {
            "source": "spotify",
            "title": "Pookkal Pookkum",
            "url": "https://open.spotify.com/track/pookkal",  # Duplicate
            "category": "music",
        },
        {
            "source": "spotify",
            "title": "Vaseegara",
            "url": "https://open.spotify.com/track/vaseegara",  # New
            "category": "music",
        },
    ]

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_recommendation_intent", return_value=mock_intent), \
         patch.object(youtube_provider, "_ensure_configured", return_value=None), \
         patch.object(youtube_provider, "search_videos", return_value=[]), \
         patch.object(spotify_provider, "_ensure_configured", return_value=None), \
         patch.object(spotify_provider, "search_tracks", return_value=mock_spotify_items):

        rec_service = RecommendationService(db_session)
        items = await rec_service.evaluate_and_fetch_recommendations(conv.id)

        # Only the new track should be persisted, duplicate suppressed
        assert len(items) == 1
        assert items[0].url == "https://open.spotify.com/track/vaseegara"


@pytest.mark.asyncio
async def test_explicit_recommendation_request_endpoint(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    conv = Conversation(is_group=True, title="Travel Ideas", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"))
    await db_session.commit()

    mock_place_items = [
        {
            "source": "tavily",
            "title": "Top 10 Places to Visit in Ooty",
            "url": "https://travelblog.example.com/ooty-guide",
            "snippet": "Botanical gardens, tea estates, and Nilgiri Mountain Railway.",
            "category": "place",
        }
    ]

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(tavily_provider, "_ensure_configured", return_value=None), \
         patch.object(tavily_provider, "search", return_value=mock_place_items), \
         patch.object(youtube_provider, "_ensure_configured", return_value=None), \
         patch.object(youtube_provider, "search_videos", return_value=[]):

        resp = await client.post(
            f"/api/v1/conversations/{conv.id}/recommendations/request",
            headers=auth_headers,
            json={"query": "Ooty tourist places", "category": "place"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["title"] == "Top 10 Places to Visit in Ooty"
        assert items[0]["url"] == "https://travelblog.example.com/ooty-guide"
        # Verify no credentials leaked
        payload_str = str(items)
        assert "api_key" not in payload_str
        assert "client_secret" not in payload_str


@pytest.mark.asyncio
async def test_empty_results_handled_without_fake_content(
    db_session: AsyncSession, test_user: User
):
    _last_recommendation_time.clear()

    conv = Conversation(is_group=True, title="Obscure Topic", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    msg = Message(conversation_id=conv.id, sender_id=test_user.id, content="Search for something obscure")
    db_session.add(msg)
    await db_session.commit()

    mock_intent = {
        "has_intent": True,
        "category": "web",
        "query": "NonexistentQuery123456789",
        "preferred_providers": ["tavily"],
    }

    # Provider returns empty results
    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_recommendation_intent", return_value=mock_intent), \
         patch.object(tavily_provider, "_ensure_configured", return_value=None), \
         patch.object(tavily_provider, "search", return_value=[]), \
         patch.object(youtube_provider, "_ensure_configured", return_value=None), \
         patch.object(youtube_provider, "search_videos", return_value=[]):

        rec_service = RecommendationService(db_session)
        items = await rec_service.evaluate_and_fetch_recommendations(conv.id)
        assert items == []


@pytest.mark.asyncio
async def test_provider_failures_do_not_break_messaging(
    db_session: AsyncSession, test_user: User
):
    _last_recommendation_time.clear()

    conv = Conversation(is_group=True, title="Music Room", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    msg = Message(conversation_id=conv.id, sender_id=test_user.id, content="Play some new songs")
    db_session.add(msg)
    await db_session.commit()

    mock_intent = {
        "has_intent": True,
        "category": "music",
        "query": "New songs",
        "preferred_providers": ["youtube"],
    }

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_recommendation_intent", return_value=mock_intent), \
         patch.object(spotify_provider, "_ensure_configured", return_value=None), \
         patch.object(spotify_provider, "search_tracks", return_value=[]), \
         patch.object(youtube_provider, "_ensure_configured", return_value=None), \
         patch.object(youtube_provider, "search_videos", side_effect=Exception("YouTube API quota exceeded")):

        rec_service = RecommendationService(db_session)
        # Provider failure must be caught and logged safely, returning empty list without crashing
        items = await rec_service.evaluate_and_fetch_recommendations(conv.id)
        assert items == []


@pytest.mark.asyncio
async def test_extract_contextual_draft_intent_scenarios():
    from app.services.recommendation_service import extract_contextual_draft_intent

    # Scenario A: Music artist
    res_a = extract_contextual_draft_intent("I like Anirudh songs")
    assert res_a is not None
    assert res_a["has_intent"] is True
    assert res_a["category"] == "music"
    assert "Anirudh" in res_a["query"]
    assert res_a["preferred_providers"][0] == "spotify"

    # Scenario B: Explicit Spotify discussion
    res_b = extract_contextual_draft_intent("Suggest some good Tamil songs on Spotify")
    assert res_b is not None
    assert res_b["has_intent"] is True
    assert res_b["category"] == "music"
    assert "Tamil songs" in res_b["query"]
    assert res_b["preferred_providers"][0] == "spotify"

    # Scenario C: Actor alone (ambiguous, must NOT assume music!)
    res_c1 = extract_contextual_draft_intent("I like actor Vijay")
    assert res_c1 is None

    # Scenario C2: Actor with movies context
    res_c2 = extract_contextual_draft_intent("Vijay movies")
    assert res_c2 is not None
    assert res_c2["has_intent"] is True
    assert res_c2["category"] == "movie"
    assert "Vijay movies" in res_c2["query"]
    assert res_c2["preferred_providers"][0] == "youtube"

    # Scenario D: Conversation continuation
    recent_ctx = ["User: I like Anirudh's music.", "Other: Which song do you like most?"]
    res_d = extract_contextual_draft_intent("I like Hukum and...", recent_context=recent_ctx)
    assert res_d is not None
    assert res_d["has_intent"] is True
    assert res_d["category"] == "music"
    assert "Hukum" in res_d["query"]
    assert "Anirudh" in res_d["query"]

    # Scenario E: Unrelated technical discussion
    res_e = extract_contextual_draft_intent("We need to finish the project before tomorrow's deadline.")
    assert res_e is None

    # Scenario F: Negation / meta feedback suppression
    res_f = extract_contextual_draft_intent(
        "when i talk about misic then only recomend songs other wise don't recomend music and whei type or chat monitor and get to known if i type tomorrow is submission you didnot ask whether morning or afterrnoon these are mistakes and from these sentences it hsa some mistakes but till it doesnot changes automatically so fix that"
    )
    assert res_f is None

    # Scenario G: Direct negation
    assert extract_contextual_draft_intent("don't recommend songs right now") is None
    assert extract_contextual_draft_intent("Tomorrow is the submission deadline.") is None


@pytest.mark.asyncio
async def test_extract_contextual_draft_intent_website_and_shopping():
    """Regression: website/shopping requests must not fall through to music, and must not be
    classified as music even when phrased with 'suggest'/'give me' (which used to default to
    Spotify/YouTube via the generic recommendation fallback)."""
    from app.services.recommendation_service import extract_contextual_draft_intent

    # 1. "Give me a bangles website" selects website/shopping intent, not music.
    res = extract_contextual_draft_intent("give me a bangles website")
    assert res is not None and res["has_intent"] is True
    assert res["category"] in ("website", "shopping")
    assert res["preferred_providers"] == ["tavily"]
    assert "bangles" in res["query"].lower()

    # 2. "Find a website to buy shoes" does not select Spotify.
    res2 = extract_contextual_draft_intent("find a website to buy shoes")
    assert res2 is not None
    assert "spotify" not in res2["preferred_providers"]
    assert res2["preferred_providers"] == ["tavily"]
    assert "shoes" in res2["query"].lower()

    # 3. "Find the official NVIDIA website" prefers official-site phrasing in the query.
    res3 = extract_contextual_draft_intent("Find the official NVIDIA website")
    assert res3 is not None and res3["category"] == "official_website"
    assert "nvidia" in res3["query"].lower()
    assert "official" in res3["query"].lower()
    assert res3["preferred_providers"] == ["tavily"]

    # 4. "Where can I buy traditional gold-colour bangles online?" is shopping, not music.
    res4 = extract_contextual_draft_intent("Where can I buy traditional gold-colour bangles online?")
    assert res4 is not None and res4["has_intent"] is True
    assert res4["category"] == "shopping"
    assert res4["preferred_providers"] == ["tavily"]

    # 5. A phrasing that includes "suggest" must still route to shopping, not the generic
    # recommend->music fallback.
    res5 = extract_contextual_draft_intent("Can you suggest a website for bangles")
    assert res5 is not None
    assert res5["category"] in ("website", "shopping")
    assert "spotify" not in res5["preferred_providers"]


@pytest.mark.asyncio
async def test_extract_contextual_draft_intent_more_options_preserves_shopping_context():
    """'More options' after a shopping request must continue shopping, not reset to music."""
    from app.services.recommendation_service import extract_contextual_draft_intent

    recent_ctx = ["User: give me a bangles website", "Assistant: here are some shopping sites"]
    res = extract_contextual_draft_intent("More options", recent_context=recent_ctx)
    assert res is not None and res["has_intent"] is True
    assert res["category"] == "shopping"
    assert res["preferred_providers"] == ["tavily"]

    # And the same continuation phrase after a music context still goes to music.
    recent_music_ctx = ["User: I like Anirudh songs", "Assistant: here are some tracks"]
    res_music = extract_contextual_draft_intent("more", recent_context=recent_music_ctx)
    assert res_music is not None
    assert res_music["category"] == "music"


@pytest.mark.asyncio
async def test_recommendation_intent_prompt_lists_shopping_domain():
    """The LLM fallback prompt must explicitly offer a shopping/website category, since omitting
    it was the other half of the regression (the model had nowhere correct to classify these
    requests and defaulted toward music)."""
    from app.providers.base_ai_provider import BaseAIProvider

    import inspect
    source = inspect.getsource(BaseAIProvider.detect_recommendation_intent)
    assert "shopping" in source.lower()
    assert "website" in source.lower()


@pytest.mark.asyncio
async def test_draft_recommendations_endpoint(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    test_user.draft_recommendations_consent = True
    conv = Conversation(is_group=True, title="Music Chat", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))
    await db_session.commit()

    mock_spotify_items = [
        {
            "source": "spotify",
            "title": "Vaseegara - Bombay Jayashri",
            "url": "https://open.spotify.com/track/vaseegara123",
            "snippet": "Track by Bombay Jayashri • Album: Minnalae",
            "category": "music",
            "published_date": "2001-02-14",
            "extra_data": {"artist": "Bombay Jayashri", "thumbnail": "https://i.scdn.co/image/test"},
        }
    ]

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(spotify_provider, "_ensure_configured", return_value=None), \
         patch.object(spotify_provider, "search_tracks", return_value=mock_spotify_items), \
         patch.object(youtube_provider, "_ensure_configured", return_value=None), \
         patch.object(youtube_provider, "search_videos", return_value=[]):

        # Call /draft/recommendations while typing
        res = await client.post(
            "/api/v1/draft/recommendations",
            json={
                "conversation_id": str(conv.id),
                "draft": "I like Anirudh songs",
                "draft_revision": "rev-test-1",
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["draft_revision"] == "rev-test-1"
        assert data["has_intent"] is True
        assert data["category"] == "music"
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["source"] == "spotify"
        assert data["recommendations"][0]["title"] == "Vaseegara - Bombay Jayashri"
        assert data["recommendations"][0]["url"] == "https://open.spotify.com/track/vaseegara123"

        # Calling again with same query uses cache without re-hitting search
        res2 = await client.post(
            "/api/v1/draft/recommendations",
            json={
                "conversation_id": str(conv.id),
                "draft": "I like Anirudh songs",
                "draft_revision": "rev-test-2",
            },
            headers=auth_headers,
        )
        assert res2.status_code == 200
        assert res2.json()["has_intent"] is True


@pytest.mark.asyncio
async def test_query_construction_matches_each_requested_category():
    """Each documented example must produce a query/category that actually targets what was
    asked, not a generic or carried-over topic."""
    from app.services.recommendation_service import extract_contextual_draft_intent

    cases = [
        ("Give me a website to buy bangles online", "shopping", ["bangles"], []),
        ("Find websites to learn Java", "website", ["java"], ["buy", "bangles"]),
        ("Find websites to learn Python", "website", ["python"], ["buy"]),
        ("Give me the official NVIDIA website", "official_website", ["nvidia", "official"], ["buy"]),
        ("Find a website to buy men watches", "shopping", ["watch"], ["java"]),
        ("Give me websites to buy laptops", "shopping", ["laptop"], ["java"]),
        ("Find websites for free coding practice", "website", ["coding"], ["buy"]),
        ("Find a website to create a resume", "website", ["resume"], ["buy"]),
        ("Suggest websites to book train tickets in India", "website", ["train"], ["buy"]),
    ]
    for text, expected_category, must_contain, must_not_contain in cases:
        res = extract_contextual_draft_intent(text)
        assert res is not None and res["has_intent"] is True, f"no intent for: {text!r}"
        assert res["category"] == expected_category, f"{text!r} -> {res['category']} (expected {expected_category})"
        assert res["preferred_providers"] == ["tavily"], f"{text!r} should be tavily-only"
        q = res["query"].lower()
        for term in must_contain:
            assert term in q, f"{text!r} -> query {q!r} missing {term!r}"
        for term in must_not_contain:
            assert term not in q, f"{text!r} -> query {q!r} unexpectedly contains {term!r}"


@pytest.mark.asyncio
async def test_topic_switch_sequence_does_not_leak_between_unrelated_requests(db_session: AsyncSession, test_user: User, test_user_b: User):
    """Regression for the reported bug: bangles -> Java -> laptops -> NVIDIA in the same
    conversation must each independently classify and query for their own topic."""
    from app.services.recommendation_service import extract_contextual_draft_intent

    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()

    history = []
    sequence = [
        ("Give me a website to buy bangles online", "shopping", "bangles"),
        ("Find websites to learn Java", "website", "java"),
        ("Find websites to buy laptops online", "shopping", "laptop"),
        ("Give me the official NVIDIA website", "official_website", "nvidia"),
    ]
    for text, expected_category, expected_term in sequence:
        res = extract_contextual_draft_intent(text, recent_context=history)
        assert res is not None and res["category"] == expected_category
        assert expected_term in res["query"].lower()
        history.append(type("M", (), {"content": text})())


@pytest.mark.asyncio
async def test_website_search_ranks_relevant_results_above_stale_unrelated_ones():
    """Even if a provider (or an upstream cache mix-up) returns a result left over from a
    different topic, relevant results must be ranked ahead of it."""
    from app.services.recommendation_service import RecommendationService

    results = [
        {"source": "tavily", "title": "Traditional Bangles Online Store", "url": "https://banglesstore.example.com", "snippet": "Buy bangles online", "category": "shopping", "extra_data": {"relevance_score": 0.4}},
        {"source": "tavily", "title": "Learn Java Programming - Free Tutorials", "url": "https://javatutorials.example.com", "snippet": "Java courses and tutorials for beginners", "category": "website", "extra_data": {"relevance_score": 0.9}},
        {"source": "tavily", "title": "Codecademy: Learn Java", "url": "https://codecademy.example.com/java", "snippet": "Interactive Java practice", "category": "website", "extra_data": {"relevance_score": 0.8}},
    ]
    ranked = RecommendationService._rank_website_results(
        results, query="java learning tutorials", official=False, entity="java"
    )
    assert ranked[0]["url"] in (
        "https://javatutorials.example.com",
        "https://codecademy.example.com/java",
    )
    # Exact-keyword enforcement: a result that mentions none of the requested terms (the
    # bangles store, left over from an unrelated search) is dropped entirely, not just ranked last.
    urls = {r["url"] for r in ranked}
    assert "https://banglesstore.example.com" not in urls
    assert len(ranked) == 2


@pytest.mark.asyncio
async def test_official_site_request_ranks_matching_domain_first():
    from app.services.recommendation_service import RecommendationService

    results = [
        {"source": "tavily", "title": "NVIDIA mentioned in tech roundup", "url": "https://technews.example.com/roundup", "snippet": "NVIDIA announced new GPUs among other companies", "category": "official_website", "extra_data": {"relevance_score": 0.5}},
        {"source": "tavily", "title": "NVIDIA - World Leader in AI Computing", "url": "https://www.nvidia.example.com", "snippet": "Official NVIDIA site", "category": "official_website", "extra_data": {"relevance_score": 0.5}},
    ]
    ranked = RecommendationService._rank_website_results(results, query="nvidia official website", official=True)
    assert ranked[0]["url"] == "https://www.nvidia.example.com"


@pytest.mark.asyncio
async def test_website_search_failure_does_not_fall_back_to_youtube_or_spotify(db_session: AsyncSession, test_user: User, test_user_b: User):
    """Requirement: a failed/unavailable website search must never silently substitute Spotify
    or YouTube results."""
    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()
    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member"),
    ])
    await db_session.commit()
    msg = Message(conversation_id=conv.id, sender_id=test_user.id, content="give me a bangles website")
    db_session.add(msg)
    await db_session.commit()

    with patch.object(Settings, "is_provider_configured", side_effect=lambda p: p in ("nvidia",)), \
         patch.object(youtube_provider, "search_videos", new_callable=AsyncMock) as mock_yt, \
         patch.object(spotify_provider, "search_tracks", new_callable=AsyncMock) as mock_sp:
        rec_service = RecommendationService(db_session)
        items = await rec_service.evaluate_and_fetch_recommendations(conv.id, triggering_message_id=msg.id)

    assert items == []
    mock_yt.assert_not_called()
    mock_sp.assert_not_called()


@pytest.mark.asyncio
async def test_missing_tavily_credentials_reported_clearly_in_draft_evaluation(db_session: AsyncSession, test_user: User, test_user_b: User):
    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()
    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member"),
    ])
    await db_session.commit()

    with patch.object(Settings, "is_provider_configured", return_value=False):
        rec_service = RecommendationService(db_session)
        result = await rec_service.evaluate_draft_recommendations(conv.id, "give me a bangles website", test_user.id)

    assert result["has_intent"] is True
    assert result["recommendations"] == []
    assert result.get("provider_unavailable") == "tavily"


@pytest.mark.asyncio
async def test_more_options_after_shopping_request_continues_shopping_not_music():
    from app.services.recommendation_service import extract_contextual_draft_intent

    history = [type("M", (), {"content": "give me a bangles website"})()]
    res = extract_contextual_draft_intent("more options", recent_context=history)
    assert res is not None and res["category"] == "shopping"
    assert res["preferred_providers"] == ["tavily"]


@pytest.mark.asyncio
async def test_existing_music_and_movie_flows_still_work_alongside_website_detection():
    from app.services.recommendation_service import extract_contextual_draft_intent

    music = extract_contextual_draft_intent("Recommend Tamil songs")
    assert music is not None and music["category"] == "music"

    movie = extract_contextual_draft_intent("Suggest some Tamil movies")
    assert movie is not None and movie["category"] == "movie"


@pytest.mark.asyncio
async def test_generic_website_request_without_a_named_subject_uses_filler_stripping_and_context():
    """Regression: 'give some website links' (no exact phrasing REQUEST_PREFIXES covers, and no
    product named) must not send a query full of leftover filler words like 'give'/'some' to
    Tavily, and must recover the real subject from the conversation when nothing was named."""
    from app.services.recommendation_service import extract_contextual_draft_intent

    # With no context and no subject named, there is nothing to search for -- must not send a
    # query built from leftover filler words ("give", "some", "links") to Tavily.
    res = extract_contextual_draft_intent("give some website links")
    assert res is None

    # With prior context naming a real subject, the same phrasing reuses that subject.
    history = [type("M", (), {"content": "I need bangles for a wedding"})()]
    res2 = extract_contextual_draft_intent("give some website links", recent_context=history)
    assert res2 is not None and res2["has_intent"] is True
    assert "bangles" in res2["query"].lower()
    assert res2["entity"] and "bangles" in res2["entity"].lower()


@pytest.mark.asyncio
async def test_rank_website_results_drops_results_with_no_keyword_match_to_the_named_subject():
    """'Exact keyword matching': once the user names a subject (e.g. 'bangles'), a result that
    mentions none of that subject's terms must not be presented as an answer."""
    from app.services.recommendation_service import RecommendationService

    results = [
        {"source": "tavily", "title": "Random unrelated blog post", "url": "https://blog.example.com/post", "snippet": "Thoughts on productivity", "extra_data": {"relevance_score": 0.6}},
        {"source": "tavily", "title": "Buy Bangles Online - Indian Jewelry", "url": "https://bangles.example.com", "snippet": "Traditional gold and silver bangles", "extra_data": {"relevance_score": 0.3}},
    ]
    ranked = RecommendationService._rank_website_results(results, query="buy bangles online online store shopping", entity="bangles")
    urls = [r["url"] for r in ranked]
    assert urls == ["https://bangles.example.com"]


@pytest.mark.asyncio
async def test_rank_website_results_falls_back_to_full_list_when_nothing_matches():
    """If literally nothing matches the subject terms, don't return an empty result set --
    keep the provider's own ranking rather than discarding everything."""
    from app.services.recommendation_service import RecommendationService

    results = [
        {"source": "tavily", "title": "Totally unrelated page", "url": "https://a.example.com", "snippet": "nothing relevant here", "extra_data": {"relevance_score": 0.5}},
    ]
    ranked = RecommendationService._rank_website_results(results, query="zzqqxx nonexistent term", entity="zzqqxx")
    assert len(ranked) == 1

