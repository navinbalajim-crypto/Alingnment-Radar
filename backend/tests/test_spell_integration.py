"""Draft spelling through /draft/analyze: provider failure fallback and no side effects."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.alignment import AlignmentFinding
from app.models.analysis_job import MessageAnalysisJob
from app.models.message import Message
from tests.test_draft_consent import CONFIGURED, GQ_ANALYZE, NV_ANALYZE, analyze_body, call
from tests.test_draft_suggest import _reset_service, world  # noqa: F401

DRAFT = "the project is delay because of yuo so qick it fast"


async def counts(db):
    return [(await db.execute(select(func.count()).select_from(m))).scalar_one() for m in (Message, AlignmentFinding, MessageAnalysisJob)]


@pytest.mark.asyncio
async def test_groq_and_nvidia_failure_fall_back_to_local_corrections(db_session, world):
    await call(db_session, world["alice"], "PUT", "/users/me/ai-preferences", {"ai_draft_analysis": True})
    boom = AsyncMock(side_effect=RuntimeError("provider down"))
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, boom), patch(GQ_ANALYZE, boom):
        resp = await call(db_session, world["alice"], "POST", "/draft/analyze", analyze_body(world, DRAFT))
    assert resp.status_code == 200
    body = resp.json()
    assert {c["original"] for c in body["corrections"]} >= {"yuo", "qick"}
    assert body["corrected_text"] == "the project is delay because of you so quick it fast"


@pytest.mark.asyncio
async def test_local_correction_without_consent_is_complete_and_calls_nobody(db_session, world):
    boom = AsyncMock(side_effect=AssertionError("external provider called"))
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, boom), patch(GQ_ANALYZE, boom):
        resp = await call(db_session, world["alice"], "POST", "/draft/analyze", analyze_body(world, DRAFT))
    body = resp.json()
    assert body["ai_consent_required"] is True
    assert body["corrected_text"] == "the project is delay because of you so quick it fast"


@pytest.mark.asyncio
async def test_draft_analysis_never_creates_messages_findings_or_jobs(db_session, world):
    before = await counts(db_session)
    with patch(CONFIGURED, return_value=True), patch(NV_ANALYZE, AsyncMock(return_value=None)), patch(GQ_ANALYZE, AsyncMock(return_value=None)):
        for consent in (False, True):
            await call(db_session, world["alice"], "PUT", "/users/me/ai-preferences", {"ai_draft_analysis": consent})
            for draft in ("tomorrow is submission", DRAFT, "can you recieve it"):
                await call(db_session, world["alice"], "POST", "/draft/analyze", analyze_body(world, draft))
    assert await counts(db_session) == before
