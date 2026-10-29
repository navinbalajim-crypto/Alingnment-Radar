"""Tests for the opt-in /draft/suggest autocomplete endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import fastapi_app
from app.models.alignment import AlignmentFinding
from app.models.analysis_job import MessageAnalysisJob
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User
from app.services import autocomplete_service as svc_module
from app.services.autocomplete_service import autocomplete_service

GROQ_CONFIGURED = "app.providers.groq_provider.GroqProvider.is_configured"
GROQ_SUGGEST = "app.providers.groq_provider.GroqProvider.suggest_completions"


@pytest.fixture(autouse=True)
def _reset_service():
    autocomplete_service._cache.clear()
    autocomplete_service._hits.clear()
    yield


async def _mk_user(db, name):
    user = User(email=f"{name}@test.com", username=name, username_normalized=name, display_name=name.title(), is_active=True)
    db.add(user)
    await db.flush()
    return user


async def _mk_conv(db, members, texts, is_group=False):
    if is_group:
        conv = Conversation(is_group=True, title="Team")
    else:
        conv = Conversation(is_group=False, direct_user_low_id=min(m.id for m in members), direct_user_high_id=max(m.id for m in members))
    db.add(conv)
    await db.flush()
    for m in members:
        db.add(ConversationMember(conversation_id=conv.id, user_id=m.id, role="member"))
    for sender, text in texts:
        db.add(Message(conversation_id=conv.id, sender_id=sender.id, content=text, message_type="text"))
    await db.flush()
    return conv


@pytest_asyncio.fixture
async def world(db_session):
    alice, bob, carol = [await _mk_user(db_session, n) for n in ("alice", "bob", "carol")]
    direct = await _mk_conv(db_session, [alice, bob], [(bob, "Is the report due soon?")])
    group = await _mk_conv(db_session, [alice, bob, carol], [(carol, "SECRET group budget talk")], is_group=True)
    await db_session.commit()
    return {"alice": alice, "bob": bob, "carol": carol, "direct": direct, "group": group}


async def _post(db_session, user, conv_id, draft, consent=True, rev="rev-1"):
    # Consent is stored server-side; the request body cannot grant it.
    user.ai_autocomplete_consent = consent
    async def override_db():
        yield db_session

    async def override_auth():
        return user

    fastapi_app.dependency_overrides.update({get_db: override_db, get_current_user: override_auth})
    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            return await client.post(
                "/api/v1/draft/suggest",
                json={"draft": draft, "conversation_id": str(conv_id), "draft_revision": rev, "ai_consent": True},
            )
    finally:
        fastapi_app.dependency_overrides.clear()


def _suggestions(*texts):
    return {"suggestions": [{"text": t} for t in texts]}


@pytest.mark.asyncio
async def test_partial_input_returns_relevant_suggestions_and_filters_unrelated(db_session, world):
    reply = _suggestions(
        "Tomorrow is the submission deadline.",
        "tomorrow is submission day",
        "Let's grab lunch on Friday",  # unrelated to the draft: must be dropped
    )
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, new_callable=AsyncMock, return_value=reply):
        resp = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
    body = resp.json()
    assert resp.status_code == 200
    assert body["ai_available"] is True
    assert [s["text"] for s in body["suggestions"]] == ["Tomorrow is the submission deadline.", "tomorrow is submission day"]
    assert body["draft_revision"] == "rev-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("draft", ["", "   ", "hi", "ok  ", "Thanks for the update.", "Is it done?"])
async def test_empty_short_or_finished_drafts_never_call_provider(db_session, world, draft):
    mock = AsyncMock(return_value=_suggestions("x"))
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, mock):
        resp = await _post(db_session, world["alice"], world["direct"].id, draft or " ")
    assert resp.status_code in (200, 422)
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_without_consent_provider_is_never_called(db_session, world):
    mock = AsyncMock(return_value=_suggestions("tomorrow is submission day"))
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, mock):
        resp = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub", consent=False)
    assert resp.json()["suggestions"] == []
    assert resp.json()["ai_available"] is False
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_provider_failure_or_missing_provider_degrades_to_empty(db_session, world):
    failing = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, failing):
        resp = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
    assert resp.status_code == 200
    assert resp.json() == {"draft_revision": "rev-1", "suggestions": [], "ai_available": False}

    with patch(GROQ_CONFIGURED, return_value=False):
        resp = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is subm")
    assert resp.status_code == 200 and resp.json()["ai_available"] is False


@pytest.mark.asyncio
async def test_malformed_provider_output_is_ignored(db_session, world):
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, new_callable=AsyncMock, return_value={"suggestions": "nope"}):
        resp = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
    assert resp.status_code == 200 and resp.json()["suggestions"] == []


@pytest.mark.asyncio
async def test_non_member_is_forbidden_and_provider_not_called(db_session, world):
    mock = AsyncMock(return_value=_suggestions("tomorrow is submission day"))
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, mock):
        resp = await _post(db_session, world["carol"], world["direct"].id, "tomorrow is sub")
    assert resp.status_code == 403
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_context_is_limited_to_the_requested_conversation(db_session, world):
    mock = AsyncMock(return_value=_suggestions("tomorrow is submission day"))
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, mock):
        await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
    sent = " ".join(m["content"] for m in mock.call_args.kwargs["conversation_context"])
    assert "Is the report due soon?" in sent
    assert "SECRET" not in sent

    mock.reset_mock()
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, mock):
        await _post(db_session, world["alice"], world["group"].id, "tomorrow is sub")
    sent = " ".join(m["content"] for m in mock.call_args.kwargs["conversation_context"])
    assert "SECRET group budget talk" in sent
    assert "report due soon" not in sent


@pytest.mark.asyncio
async def test_repeated_request_is_cached_and_rate_limited(db_session, world, monkeypatch):
    mock = AsyncMock(return_value=_suggestions("tomorrow is submission day"))
    monkeypatch.setattr(svc_module, "RATE_LIMIT_REQUESTS", 2)
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, mock):
        for _ in range(3):
            r = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
            assert r.json()["suggestions"]
        assert mock.await_count == 1  # cache hits do not re-call the provider

        await _post(db_session, world["alice"], world["direct"].id, "tomorrow is su")
        await _post(db_session, world["alice"], world["direct"].id, "tomorrow is s")
        limited = await _post(db_session, world["alice"], world["direct"].id, "tomorrow i")
    assert mock.await_count == 2
    assert limited.json()["suggestions"] == [] and limited.json()["ai_available"] is False


@pytest.mark.asyncio
async def test_autocomplete_creates_no_messages_findings_or_jobs(db_session, world):
    async def counts():
        return [
            (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
            for model in (Message, AlignmentFinding, MessageAnalysisJob)
        ]

    before = await counts()
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, new_callable=AsyncMock, return_value=_suggestions("tomorrow is submission day")):
        await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
    assert await counts() == before


@pytest.mark.asyncio
async def test_response_never_contains_secrets(db_session, world):
    with patch(GROQ_CONFIGURED, return_value=True), patch(GROQ_SUGGEST, new_callable=AsyncMock, return_value=_suggestions("tomorrow is submission day")):
        resp = await _post(db_session, world["alice"], world["direct"].id, "tomorrow is sub")
    assert set(resp.json()) == {"draft_revision", "suggestions", "ai_available"}
    assert "gsk_" not in resp.text and "Bearer" not in resp.text
