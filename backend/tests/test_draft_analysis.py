"""Tests for draft analysis (writing correction, completions, and context-aware behavior)."""

import uuid
from unittest.mock import AsyncMock, patch, PropertyMock
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import fastapi_app
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User


@pytest_asyncio.fixture
async def setup_conversation(db_session: AsyncSession):
    alice = User(
        email="alice@test.com", username="alice",
        username_normalized="alice", display_name="Alice", is_active=True,
        ai_draft_analysis_consent=True, draft_recommendations_consent=True,
    )
    bob = User(
        email="bob@test.com", username="bob",
        username_normalized="bob", display_name="Bob", is_active=True,
    )
    db_session.add_all([alice, bob])
    await db_session.flush()

    conv = Conversation(is_group=False, direct_user_low_id=min(alice.id, bob.id), direct_user_high_id=max(alice.id, bob.id))
    db_session.add(conv)
    await db_session.flush()

    m1 = ConversationMember(conversation_id=conv.id, user_id=alice.id, role="member")
    m2 = ConversationMember(conversation_id=conv.id, user_id=bob.id, role="member")
    db_session.add_all([m1, m2])

    msg1 = Message(conversation_id=conv.id, sender_id=alice.id, content="Please send the report by end of day.", message_type="text")
    msg2 = Message(conversation_id=conv.id, sender_id=bob.id, content="Sure, I'll work on it now.", message_type="text")
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    return {"alice": alice, "bob": bob, "conversation": conv}


def _make_overrides(db_session, user):
    async def override_get_db():
        yield db_session
    async def override_auth():
        return user
    return {get_db: override_get_db, get_current_user: override_auth}


def _mock_nvidia(corrections=None, completions=None, tone="professional", corrected_text=None):
    return {
        "tone": tone,
        "corrected_text": corrected_text,
        "corrections": corrections or [],
        "completions": completions or [],
    }


async def _post_draft(overrides, draft, conv_id, revision):
    fastapi_app.dependency_overrides.update(overrides)
    try:
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/v1/draft/analyze", json={
                "draft": draft,
                "conversation_id": str(conv_id),
                "draft_revision": revision,
            })
    finally:
        fastapi_app.dependency_overrides.clear()


class TestDraftAnalysis:

    @pytest.mark.asyncio
    async def test_bcoz_expanded_in_professional_context(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        mock_result = _mock_nvidia(
            corrections=[{"original": "bcoz", "corrected": "because", "reason": "Abbreviation expansion", "confidence": 0.95}],
            corrected_text="I will send the report tomorrow because I am working on it.",
        )

        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=mock_result):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "I will send the report tmrw bcoz I am working on it.", data["conversation"].id, "rev-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["draft_revision"] == "rev-1"
        assert len(body["corrections"]) >= 1
        assert body["corrections"][0]["original"] == "bcoz"
        assert body["corrections"][0]["corrected"] == "because"

    @pytest.mark.asyncio
    async def test_misspelled_word_corrected(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        mock_result = _mock_nvidia(
            corrections=[{"original": "elaphant", "corrected": "elephant", "reason": "Spelling", "confidence": 0.99}],
            corrected_text="I saw an elephant at the zoo.",
        )

        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=mock_result):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "I saw an elaphant at the zoo.", data["conversation"].id, "rev-2")

        assert resp.status_code == 200
        assert any(c["corrected"] == "elephant" for c in resp.json()["corrections"])

    @pytest.mark.asyncio
    async def test_casual_slang_preserved(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        mock_result = _mock_nvidia(corrections=[], corrected_text=None, tone="casual")

        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=mock_result):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "bro that match was crazy lol", data["conversation"].id, "rev-3")

        assert resp.status_code == 200
        body = resp.json()
        assert body["corrections"] == []
        assert body["corrected_text"] is None
        assert body["tone"] == "casual"

    @pytest.mark.asyncio
    async def test_stale_draft_revision_echoed(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])

        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=_mock_nvidia()):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "Hello world test message", data["conversation"].id, "rev-unique-42")

        assert resp.status_code == 200
        assert resp.json()["draft_revision"] == "rev-unique-42"

    @pytest.mark.asyncio
    async def test_ai_failure_does_not_break_endpoint(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])

        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, side_effect=Exception("NVIDIA down")):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "Testing AI failure gracefully", data["conversation"].id, "rev-fail")

        assert resp.status_code == 200
        body = resp.json()
        assert body["corrections"] == []
        assert body["completions"] == []

    @pytest.mark.asyncio
    async def test_draft_completions_returned(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        mock_result = _mock_nvidia(completions=[
            {"text": "I will send the final report tomorrow.", "confidence": 0.85},
            {"text": "I will send the updated document shortly.", "confidence": 0.72},
        ])

        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=mock_result):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "I will send the", data["conversation"].id, "rev-comp")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["completions"]) == 2
        assert "final report" in body["completions"][0]["text"]

    @pytest.mark.asyncio
    async def test_unauthorized_conversation_rejected(self, db_session, setup_conversation):
        data = setup_conversation
        outsider = User(email="eve@test.com", username="eve", username_normalized="eve", display_name="Eve", is_active=True)
        db_session.add(outsider)
        await db_session.commit()

        overrides = _make_overrides(db_session, outsider)
        with patch("app.core.config.Settings.is_provider_configured", return_value=True):
            resp = await _post_draft(overrides, "sneaky draft", data["conversation"].id, "rev-unauth")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_nvidia_unconfigured_returns_empty(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])

        with patch("app.core.config.Settings.is_provider_configured", return_value=False):
            resp = await _post_draft(overrides, "testing unconfigured provider", data["conversation"].id, "rev-noconfig")

        assert resp.status_code == 200
        body = resp.json()
        assert body["corrections"] == []
        assert body["completions"] == []
        assert body["ai_available"] is False

    @pytest.mark.asyncio
    async def test_provider_failure_flags_ai_unavailable(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, side_effect=Exception("timeout")):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "Testing provider timeout", data["conversation"].id, "rev-x")
        assert resp.status_code == 200
        assert resp.json()["ai_available"] is False

    @pytest.mark.asyncio
    async def test_punctuation_only_and_noop_corrections_dropped(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        draft = "We can't approve it unless legal signs off"
        mock_result = _mock_nvidia(
            corrections=[
                {"original": draft, "corrected": draft + ".", "reason": "punctuation", "confidence": 0.9},
                {"original": "legal", "corrected": "legal", "reason": "noop", "confidence": 0.9},
            ],
            corrected_text=draft + ".",
        )
        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=mock_result):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, draft, data["conversation"].id, "rev-p")
        body = resp.json()
        assert body["corrections"] == []
        assert body["corrected_text"] is None
        assert body["ai_available"] is True

    @pytest.mark.asyncio
    async def test_completions_skipped_for_finished_sentence_and_unrelated_text(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        finished = _mock_nvidia(completions=[{"text": "The meeting is on Monday. Bring the agenda.", "confidence": 0.8}])
        partial = _mock_nvidia(completions=[
            {"text": "Can we move the review to Friday?", "confidence": 0.8},
            {"text": "Something unrelated entirely", "confidence": 0.8},
            {"text": "Can we move the review to next week?", "confidence": 0.7},
            {"text": "Can we move the review to Monday?", "confidence": 0.6},
        ])
        with patch("app.core.config.Settings.is_provider_configured", return_value=True):
            with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=finished):
                r1 = await _post_draft(overrides, "The meeting is on Monday.", data["conversation"].id, "rev-f")
            with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=partial):
                r2 = await _post_draft(overrides, "Can we move the review to", data["conversation"].id, "rev-q")
        assert r1.json()["completions"] == []
        texts = [c["text"] for c in r2.json()["completions"]]
        assert texts == ["Can we move the review to Friday?", "Can we move the review to next week?"]

    @pytest.mark.asyncio
    async def test_malformed_provider_shapes_do_not_crash(self, db_session, setup_conversation):
        data = setup_conversation
        overrides = _make_overrides(db_session, data["alice"])
        weird = {"tone": 5, "corrected_text": ["x"], "corrections": "oops", "completions": [None, "str", {"text": None}]}
        with patch("app.providers.nvidia_provider.NvidiaProvider.analyze_draft", new_callable=AsyncMock, return_value=weird):
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                resp = await _post_draft(overrides, "A draft that is unfinished", data["conversation"].id, "rev-w")
        assert resp.status_code == 200
        body = resp.json()
        assert body["corrections"] == [] and body["completions"] == [] and body["tone"] is None


class TestDraftProviderCall:

    @pytest.mark.asyncio
    async def test_draft_call_disables_reasoning_and_uses_short_timeout(self):
        from app.providers.nvidia_provider import DRAFT_TIMEOUT_SECONDS, nvidia_provider

        fake = {"choices": [{"message": {"content": '{"tone": "casual", "corrected_text": null, "corrections": [], "completions": []}'}}]}
        with patch.object(type(nvidia_provider), "_post_chat_completion", new_callable=AsyncMock, return_value=fake) as post:
            with patch("app.core.config.Settings.is_provider_configured", return_value=True):
                result = await nvidia_provider.analyze_draft(draft="hello there friend", conversation_context=[])
        kwargs = post.call_args.kwargs
        assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
        assert kwargs["timeout"] == DRAFT_TIMEOUT_SECONDS <= 15
        assert result["tone"] == "casual"

    @pytest.mark.asyncio
    async def test_spelling_engine_corrections_and_sentence_optimization(self):
        from app.services.spelling_engine import get_spelling_corrections

        # Test user-reported typos
        corrections, corrected_text = get_spelling_corrections("misic recomend didnot afterrnoon hsa doesnot")
        corr_map = {c["original"]: c["corrected"] for c in corrections}
        assert corr_map["misic"] == "music"
        assert corr_map["recomend"] == "recommend"
        assert corr_map["didnot"] == "did not"
        assert corr_map["afterrnoon"] == "afternoon"
        assert corr_map["hsa"] == "has"
        assert corr_map["doesnot"] == "does not"

        # Test whei -> when I
        corrections_whei, _ = get_spelling_corrections("whei type")
        assert any(c["corrected"] == "when I" for c in corrections_whei)

        # Test sentence phrasing optimization
        corrections_sub, text_sub = get_spelling_corrections("tomorrow is submission")
        assert text_sub == "The submission is due tomorrow."
