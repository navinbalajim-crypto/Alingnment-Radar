"""Server-side consent enforcement for every path that sends an unsent draft to an external service."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import fastapi_app
from app.models.user import User
from app.services.spelling_engine import get_spelling_corrections
from tests.test_analysis_queue import jobs, use_ai, enqueue_all  # noqa: F401  (reused helpers)
from tests.test_alignment_dedup import add_msg, make_conv, result
from tests.test_draft_suggest import _reset_service, world  # noqa: F401  (fixtures)
from app.services.analysis_queue import process_conversation_jobs

CONFIGURED = "app.core.config.Settings.is_provider_configured"
NV_ANALYZE = "app.providers.nvidia_provider.NvidiaProvider.analyze_draft"
GQ_ANALYZE = "app.providers.groq_provider.GroqProvider.analyze_draft"
GQ_SUGGEST = "app.providers.groq_provider.GroqProvider.suggest_completions"
CLOUD_RESULT = {"tone": "professional", "corrected_text": None, "corrections": [], "completions": [{"text": "Please send the report today"}]}

TYPO_DRAFT = "I saw an elaphant tmrw bcoz it was fun"


async def call(db_session, user, method, path, json=None):
    async def override_db():
        yield db_session

    async def override_auth():
        return user

    fastapi_app.dependency_overrides.update({get_db: override_db, get_current_user: override_auth})
    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            return await client.request(method, f"/api/v1{path}", json=json)
    finally:
        fastapi_app.dependency_overrides.clear()


def analyze_body(world, draft=TYPO_DRAFT, **extra):
    return {"draft": draft, "conversation_id": str(world["direct"].id), "draft_revision": "r1", **extra}


def provider_mocks():
    return AsyncMock(return_value=CLOUD_RESULT), AsyncMock(return_value=CLOUD_RESULT), AsyncMock(return_value={"suggestions": [{"text": "x"}]})


@pytest.mark.asyncio
async def test_new_users_default_to_no_consent(db_session, world):
    assert (await call(db_session, world["alice"], "GET", "/users/me/ai-preferences")).json() == {
        "ai_draft_analysis": False, "ai_autocomplete": False, "draft_recommendations": False,
    }
    for col in ("ai_draft_analysis_consent", "ai_autocomplete_consent", "draft_recommendations_consent"):
        assert getattr(world["alice"], col) is False


@pytest.mark.asyncio
async def test_no_external_provider_is_called_without_consent(db_session, world):
    nv, gq, sug = provider_mocks()
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, nv), patch(GQ_ANALYZE, gq), patch(GQ_SUGGEST, sug):
        analyze = await call(db_session, world["alice"], "POST", "/draft/analyze", analyze_body(world))
        suggest = await call(db_session, world["alice"], "POST", "/draft/suggest", analyze_body(world, "Please send the"))
        recs = await call(db_session, world["alice"], "POST", "/draft/recommendations", analyze_body(world, "play some Tamil songs"))
    nv.assert_not_called()
    gq.assert_not_called()
    sug.assert_not_called()
    assert analyze.status_code == 200 and analyze.json()["ai_available"] is False and analyze.json()["ai_consent_required"] is True
    assert suggest.json()["suggestions"] == []
    assert recs.json()["recommendations"] == [] and recs.json()["has_intent"] is False


@pytest.mark.asyncio
async def test_local_spelling_still_works_without_consent(db_session, world):
    expected = {c["original"] for c in get_spelling_corrections(TYPO_DRAFT)[0]}
    assert expected, "local engine should flag at least one typo in the fixture draft"
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, AsyncMock()) as nv:
        body = (await call(db_session, world["alice"], "POST", "/draft/analyze", analyze_body(world))).json()
    nv.assert_not_called()
    assert {c["original"] for c in body["corrections"]} == expected
    assert body["corrected_text"] and body["corrected_text"] != TYPO_DRAFT


@pytest.mark.asyncio
async def test_request_body_cannot_grant_consent(db_session, world):
    """Direct API callers cannot bypass the stored setting by sending consent-like fields."""
    nv, gq, sug = provider_mocks()
    forged = {"ai_consent": True, "ai_draft_analysis": True, "ai_draft_analysis_consent": True, "consent": True}
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, nv), patch(GQ_ANALYZE, gq), patch(GQ_SUGGEST, sug):
        await call(db_session, world["alice"], "POST", "/draft/analyze", analyze_body(world, **forged))
        await call(db_session, world["alice"], "POST", "/draft/suggest", analyze_body(world, "Please send the", **forged))
    nv.assert_not_called(); gq.assert_not_called(); sug.assert_not_called()


@pytest.mark.asyncio
async def test_providers_are_called_only_with_the_matching_consent(db_session, world):
    nv, gq, sug = provider_mocks()
    alice = world["alice"]
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, nv), patch(GQ_ANALYZE, gq), patch(GQ_SUGGEST, sug):
        # Autocomplete consent alone does not authorise draft analysis.
        put = await call(db_session, alice, "PUT", "/users/me/ai-preferences", {"ai_autocomplete": True})
        assert put.json() == {"ai_draft_analysis": False, "ai_autocomplete": True, "draft_recommendations": False}
        await call(db_session, alice, "POST", "/draft/analyze", analyze_body(world))
        nv.assert_not_called(); gq.assert_not_called()
        suggest = await call(db_session, alice, "POST", "/draft/suggest", analyze_body(world, "Please send the"))
        assert sug.await_count == 1 and suggest.json()["ai_available"] is True

        # Analysis consent enables the analysis providers.
        await call(db_session, alice, "PUT", "/users/me/ai-preferences", {"ai_draft_analysis": True})
        resp = await call(db_session, alice, "POST", "/draft/analyze", analyze_body(world))
    assert nv.await_count + gq.await_count >= 1
    assert resp.json()["ai_available"] is True and resp.json()["ai_consent_required"] is False


@pytest.mark.asyncio
async def test_revoking_consent_stops_subsequent_requests(db_session, world):
    nv, gq, sug = provider_mocks()
    alice = world["alice"]
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, nv), patch(GQ_ANALYZE, gq), patch(GQ_SUGGEST, sug):
        await call(db_session, alice, "PUT", "/users/me/ai-preferences", {"ai_draft_analysis": True, "ai_autocomplete": True})
        await call(db_session, alice, "POST", "/draft/analyze", analyze_body(world))
        await call(db_session, alice, "POST", "/draft/suggest", analyze_body(world, "Please send the"))
        analysis_calls, suggest_calls = nv.await_count + gq.await_count, sug.await_count
        assert analysis_calls >= 1 and suggest_calls == 1

        await call(db_session, alice, "PUT", "/users/me/ai-preferences", {"ai_draft_analysis": False, "ai_autocomplete": False})
        again = await call(db_session, alice, "POST", "/draft/analyze", analyze_body(world, "I saw an elaphant today ok"))
        await call(db_session, alice, "POST", "/draft/suggest", analyze_body(world, "Please send the"))  # would be a cache hit
    assert nv.await_count + gq.await_count == analysis_calls
    assert sug.await_count == suggest_calls
    assert again.json()["ai_consent_required"] is True


@pytest.mark.asyncio
async def test_one_users_consent_and_cache_never_serve_another_user(db_session, world):
    sug = AsyncMock(return_value={"suggestions": [{"text": "Please send the report today"}]})
    with patch(CONFIGURED, return_value=True), patch(GQ_SUGGEST, sug):
        await call(db_session, world["alice"], "PUT", "/users/me/ai-preferences", {"ai_autocomplete": True})
        mine = await call(db_session, world["alice"], "POST", "/draft/suggest", analyze_body(world, "Please send the"))
        assert mine.json()["suggestions"]
        # Bob is in the same conversation with the identical draft but has not opted in.
        theirs = await call(db_session, world["bob"], "POST", "/draft/suggest", analyze_body(world, "Please send the"))
    assert theirs.json() == {"draft_revision": "r1", "suggestions": [], "ai_available": False}
    assert sug.await_count == 1


@pytest.mark.asyncio
async def test_preferences_endpoint_requires_auth_and_stores_no_draft(client):
    assert (await client.get("/api/v1/users/me/ai-preferences")).status_code == 401
    assert (await client.put("/api/v1/users/me/ai-preferences", json={"ai_autocomplete": True})).status_code == 401
    assert set(User.__table__.columns.keys()) >= {"ai_draft_analysis_consent"}
    assert not [c for c in User.__table__.columns.keys() if "draft_text" in c or "draft_content" in c]


@pytest.mark.asyncio
async def test_post_message_alignment_is_independent_of_draft_consent(db_session, test_user, test_user_b):
    """Sent messages follow the separate alignment policy: analysed even though draft consent is off."""
    assert test_user.ai_draft_analysis_consent is False and test_user.ai_autocomplete_consent is False
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    await enqueue_all(db_session, conv, [m])
    mock = AsyncMock(return_value=result([m.id]))
    with use_ai(mock):
        finding, _, _ = await process_conversation_jobs(db_session, conv.id)
    assert mock.await_count == 1
    assert finding is not None
    assert [j.outcome for j in await jobs(db_session)] == ["finding_created"]
