"""Regression tests A through J for batched message analysis, multi-finding detection,
per-message coverage, deduplication, and isolation."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token
from app.db.base import Base, utc_now
from app.models.alignment import AlignmentFinding
from app.models.analysis_job import MessageAnalysisJob
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User
from app.providers.groq_provider import groq_provider
from app.providers.nvidia_provider import nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult, AlignmentFindingItem
from app.services.ai_decision_engine import AIDecisionEngine
from app.services.alignment_service import AlignmentService, _last_analysis_time
from app.services.analysis_queue import AnalysisQueue, process_conversation_jobs
from tests.test_alignment_dedup import add_msg, make_conv, resolve


def patched_ai(mock):
    return (
        patch.object(Settings, "is_provider_configured", return_value=True),
        patch.object(nvidia_provider, "_ensure_configured", return_value=None),
        patch.object(nvidia_provider, "detect_alignment", mock),
        patch.object(groq_provider, "detect_alignment", AsyncMock(return_value=None)),
    )


class use_ai_patch:
    def __init__(self, mock):
        self.patches = patched_ai(mock)

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in self.patches:
            p.stop()


async def make_user(db: AsyncSession, name: str) -> User:
    u = User(
        email=f"{name}@example.com",
        username=name,
        username_normalized=name.lower(),
        display_name=name.capitalize(),
        is_active=True,
    )
    db.add(u)
    await db.commit()
    return u


async def enqueue_msgs(db: AsyncSession, conv: Conversation, msgs):
    q = AnalysisQueue(db)
    for m in msgs:
        await q.enqueue(m.id, conv.id)
    await db.commit()


async def get_jobs(db: AsyncSession):
    res = await db.execute(select(MessageAnalysisJob).order_by(MessageAnalysisJob.created_at))
    return res.scalars().all()


async def count_findings(db: AsyncSession, conv: Conversation) -> int:
    res = await db.execute(
        select(func.count()).select_from(AlignmentFinding).where(AlignmentFinding.conversation_id == conv.id)
    )
    return res.scalar_one()


# --- Regression Test A ---
@pytest.mark.asyncio
async def test_a_three_rapid_ambiguous_messages_produce_three_distinct_findings(db_session, test_user, test_user_b):
    """A. Three rapid ambiguous messages in one batch can produce three distinct findings when all three issues are genuinely distinct."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit the report soon.", -30)
    m2 = await add_msg(db_session, conv, test_user, "Send the files to that client.", -20)
    m3 = await add_msg(db_session, conv, test_user, "Ensure they sign off on the deliverable.", -10)
    await enqueue_msgs(db_session, conv, [m1, m2, m3])

    multi_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id), str(m2.id), str(m3.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                severity="medium",
                title="Unclear Submission Deadline",
                explanation="'Soon' leaves the exact date/time undefined.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
                clarification_question="When is the report due?",
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="unclear_references",
                severity="medium",
                title="Unspecified Client",
                explanation="'That client' is unspecified.",
                confidence=0.88,
                supporting_message_ids=[str(m2.id)],
                clarification_question="Which client should receive the files?",
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="responsibilities",
                severity="medium",
                title="Unspecified Sign-off Owner",
                explanation="'They' is ambiguous.",
                confidence=0.85,
                supporting_message_ids=[str(m3.id)],
                clarification_question="Who specifically needs to sign off?",
            ),
        ],
    )

    mock = AsyncMock(return_value=multi_result)
    with use_ai_patch(mock):
        batch, retry_delay, processed = await process_conversation_jobs(db_session, conv.id)

    assert processed is True
    assert retry_delay is None
    assert batch is not None
    assert len(batch) == 3

    # Check database persistence
    findings_rows = (
        await db_session.execute(
            select(AlignmentFinding).where(AlignmentFinding.conversation_id == conv.id).order_by(AlignmentFinding.created_at)
        )
    ).scalars().all()

    assert len(findings_rows) == 3
    titles = {f.title for f in findings_rows}
    assert "Unclear Submission Deadline" in titles
    assert "Unspecified Client" in titles
    assert "Unspecified Sign-off Owner" in titles

    # Verify stable anchoring
    anchors = {f.triggered_by_message_id for f in findings_rows}
    assert {m1.id, m2.id, m3.id} == anchors

    # Verify per-message jobs are all completed with finding_created
    jobs = await get_jobs(db_session)
    assert len(jobs) == 3
    assert all(j.status == "done" for j in jobs)
    assert all(j.outcome == "finding_created" for j in jobs)


# --- Regression Test B ---
@pytest.mark.asyncio
async def test_b_same_underlying_ambiguity_produces_single_finding(db_session, test_user, test_user_b):
    """B. Two messages describe the same underlying ambiguity; only one appropriate finding is created when they represent one issue."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it soon.", -20)
    m2 = await add_msg(db_session, conv, test_user, "Yeah, let's complete it soon.", -10)
    await enqueue_msgs(db_session, conv, [m1, m2])

    multi_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id), str(m2.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                severity="medium",
                title="Vague Completion Deadline",
                explanation="The timing 'soon' is undefined.",
                confidence=0.92,
                supporting_message_ids=[str(m1.id)],
                clarification_question="What is the target completion time?",
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                severity="medium",
                title="Vague Completion Deadline",
                explanation="Repeats the vague 'soon' deadline.",
                confidence=0.88,
                supporting_message_ids=[str(m2.id)],
                clarification_question="What is the target completion time?",
            ),
        ],
    )

    mock = AsyncMock(return_value=multi_result)
    with use_ai_patch(mock):
        batch, retry_delay, processed = await process_conversation_jobs(db_session, conv.id)

    assert processed is True
    assert batch is not None
    assert len(batch) == 1  # Deduplicated into exactly 1 finding
    assert await count_findings(db_session, conv) == 1

    jobs = await get_jobs(db_session)
    assert len(jobs) == 2
    assert all(j.status == "done" for j in jobs)


# --- Regression Test C ---
@pytest.mark.asyncio
async def test_c_casual_message_not_flagged_while_distinct_ambiguities_detected(db_session, test_user, test_user_b):
    """C. A batch includes a casual message and multiple ambiguous messages; the casual message is not flagged unnecessarily, while all distinct ambiguities are detected."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m0 = await add_msg(db_session, conv, test_user, "Hi", -30)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -20)
    m2 = await add_msg(db_session, conv, test_user, "Use that template.", -10)
    await enqueue_msgs(db_session, conv, [m0, m1, m2])

    multi_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id), str(m2.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                severity="medium",
                title="Unclear Deadline",
                explanation="Tomorrow is ambiguous.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
                clarification_question="What time tomorrow?",
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="unclear_references",
                severity="medium",
                title="Unspecified Template",
                explanation="'That template' is ambiguous.",
                confidence=0.85,
                supporting_message_ids=[str(m2.id)],
                clarification_question="Which template?",
            ),
        ],
    )

    mock = AsyncMock(return_value=multi_result)
    with use_ai_patch(mock):
        batch, _, processed = await process_conversation_jobs(db_session, conv.id)

    assert processed is True
    assert len(batch) == 2

    # Verify job outcomes
    job_map = {j.message_id: j for j in await get_jobs(db_session)}
    assert job_map[m0.id].status == "done"
    assert job_map[m0.id].outcome == "skipped_casual"

    assert job_map[m1.id].status == "done"
    assert job_map[m1.id].outcome == "finding_created"

    assert job_map[m2.id].status == "done"
    assert job_map[m2.id].outcome == "finding_created"


# --- Regression Test D ---
@pytest.mark.asyncio
async def test_d_omitted_message_triggers_bounded_followup_not_silently_cleared(db_session, test_user, test_user_b):
    """D. The AI omits one eligible message from its result. The omitted message is not silently marked as adequately analyzed; bounded follow-up processing occurs when necessary."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Finish it soon.", -20)
    m2 = await add_msg(db_session, conv, test_user, "Deliver to that office.", -10)
    await enqueue_msgs(db_session, conv, [m1, m2])

    # Pass 1: AI only analyzed m1, completely omitting m2 from analyzed_message_ids
    pass1_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Soon is vague.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
            )
        ],
    )

    # Pass 2 (targeted follow-up for m2): AI returns finding for m2
    pass2_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m2.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="unclear_references",
                title="Unspecified Office",
                explanation="'That office' is unspecified.",
                confidence=0.88,
                supporting_message_ids=[str(m2.id)],
            )
        ],
    )

    mock = AsyncMock(side_effect=[pass1_result, pass2_result])
    with use_ai_patch(mock):
        batch, _, processed = await process_conversation_jobs(db_session, conv.id)

    assert processed is True
    assert mock.await_count == 2  # Bounded follow-up occurred!
    assert len(batch) == 2

    job_map = {j.message_id: j for j in await get_jobs(db_session)}
    assert job_map[m1.id].status == "done"
    assert job_map[m2.id].status == "done"


# --- Regression Test E ---
@pytest.mark.asyncio
async def test_e_failed_provider_response_does_not_mark_jobs_as_analyzed(db_session, test_user, test_user_b):
    """E. A malformed or failed provider response does not mark all jobs as successfully analyzed."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it soon.", -10)
    await enqueue_msgs(db_session, conv, [m1])

    failing_mock = AsyncMock(return_value=None)
    with use_ai_patch(failing_mock):
        batch, delay, processed = await process_conversation_jobs(db_session, conv.id)

    assert batch is None
    assert delay is not None
    assert processed is True

    job = (await get_jobs(db_session))[0]
    assert job.status == "pending"
    assert job.attempts == 1
    assert job.outcome is None  # NOT marked as checked or no_issue
    assert job.last_error == "provider_unavailable"


# --- Regression Test F ---
@pytest.mark.asyncio
async def test_f_retry_does_not_duplicate_already_persisted_findings(db_session, test_user, test_user_b):
    """F. A retry does not duplicate findings already persisted by a previous partial batch."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it soon.", -20)
    m2 = await add_msg(db_session, conv, test_user, "Send to that client.", -10)
    await enqueue_msgs(db_session, conv, [m1, m2])

    # Batch 1: m1 succeeds, but m2 is omitted and follow-up fails
    p1 = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Soon is vague.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
            )
        ],
    )

    mock = AsyncMock(side_effect=[p1, None])
    with use_ai_patch(mock):
        batch1, delay, _ = await process_conversation_jobs(db_session, conv.id)

    assert len(batch1) == 1
    assert await count_findings(db_session, conv) == 1

    # Now make m2 due for retry
    await db_session.execute(update(MessageAnalysisJob).where(MessageAnalysisJob.message_id == m2.id).values(next_attempt_at=utc_now() - timedelta(seconds=1)))
    await db_session.commit()

    # Retry returns both m1 and m2 findings
    p2 = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id), str(m2.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Soon is vague.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="unclear_references",
                title="Unspecified Client",
                explanation="Client is unspecified.",
                confidence=0.85,
                supporting_message_ids=[str(m2.id)],
            ),
        ],
    )

    mock2 = AsyncMock(return_value=p2)
    with use_ai_patch(mock2):
        batch2, _, _ = await process_conversation_jobs(db_session, conv.id)

    assert len(batch2) == 1  # Only m2 finding is new; m1 finding was deduplicated!
    assert await count_findings(db_session, conv) == 2  # Total findings in DB is exactly 2


# --- Regression Test G ---
@pytest.mark.asyncio
async def test_g_resolved_finding_not_recreated_by_multi_finding_response(db_session, test_user, test_user_b):
    """G. A resolved finding is not recreated by a multi-finding response."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it soon.", -40)

    # First finding on m1
    init_res = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Soon is vague.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
            )
        ],
    )
    with use_ai_patch(AsyncMock(return_value=init_res)):
        await enqueue_msgs(db_session, conv, [m1])
        batch, _, _ = await process_conversation_jobs(db_session, conv.id)

    f1 = batch[0]
    await resolve(db_session, AlignmentService(db_session), conv, f1.id, test_user)

    # Later new message m2
    m2 = await add_msg(db_session, conv, test_user, "Send that document.", 20)
    await enqueue_msgs(db_session, conv, [m2])

    # Multi-finding response that returns repeat of resolved m1 plus new m2
    multi_res = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id), str(m2.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Soon is vague.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="unclear_references",
                title="Unspecified Document",
                explanation="That document is unspecified.",
                confidence=0.88,
                supporting_message_ids=[str(m2.id)],
            ),
        ],
    )

    with use_ai_patch(AsyncMock(return_value=multi_res)):
        batch2, _, _ = await process_conversation_jobs(db_session, conv.id)

    assert len(batch2) == 1
    assert batch2[0].title == "Unspecified Document"
    assert await count_findings(db_session, conv) == 2

    # Verify first finding status remains resolved
    f1_row = await db_session.get(AlignmentFinding, f1.id)
    assert f1_row.status == "resolved"


# --- Regression Test G2 (dedup root-cause fix) ---
@pytest.mark.asyncio
async def test_g2_single_message_flagged_under_two_categories_in_one_batch_is_one_finding(db_session, test_user, test_user_b):
    """A single vague message (e.g. a reminder request missing both the task and a clear
    referent) can be reported by the AI as two different findings in the SAME batch -- e.g.
    'missing reminder details' (category=deadlines) and 'unclear reference' (category=
    unclear_references) -- both citing the exact same message. Since they share evidence, they
    must collapse into exactly one active finding rather than two separate cards."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Make this as reminder for our project deadline after the person is given.", -10)
    await enqueue_msgs(db_session, conv, [m1])

    multi_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m1.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                severity="medium",
                title="Missing reminder details",
                explanation="The deadline and task are not specified.",
                confidence=0.9,
                supporting_message_ids=[str(m1.id)],
                clarification_question="What is the task and exact deadline?",
            ),
            AlignmentFindingItem(
                mismatch_detected=True,
                category="unclear_references",
                severity="medium",
                title="Unclear dependency on 'the person'",
                explanation="'The person' is not identified.",
                confidence=0.85,
                supporting_message_ids=[str(m1.id)],
                clarification_question="Who is 'the person' this depends on?",
            ),
        ],
    )

    mock = AsyncMock(return_value=multi_result)
    with use_ai_patch(mock):
        batch, _, processed = await process_conversation_jobs(db_session, conv.id)

    assert processed is True
    assert len(batch) == 1  # Collapsed into one finding despite different categories/titles
    assert await count_findings(db_session, conv) == 1

    row = (await db_session.execute(select(AlignmentFinding).where(AlignmentFinding.conversation_id == conv.id))).scalar_one()
    assert row.status not in ("resolved", "dismissed")
    assert str(m1.id) in (row.supporting_message_ids or [])


# --- Regression Test H ---
@pytest.mark.asyncio
async def test_h_group_conversations_remain_isolated_and_authorized(client, db_session, test_user, test_user_b):
    """H. Group conversations remain isolated and findings are delivered only to authorized participants."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -20)
    await enqueue_msgs(db_session, conv, [m])

    res = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Tomorrow is ambiguous.",
                confidence=0.9,
                supporting_message_ids=[str(m.id)],
            )
        ],
    )
    with use_ai_patch(AsyncMock(return_value=res)):
        await process_conversation_jobs(db_session, conv.id)

    # An outsider (not member)
    outsider = await make_user(db_session, "outsider")
    token = create_access_token(user_id=str(outsider.id), username=outsider.username)
    headers = {"Authorization": f"Bearer {token}"}

    # Verify forbidden access
    r1 = await client.get(f"/api/v1/conversations/{conv.id}/ai-items", headers=headers)
    assert r1.status_code == 403

    r2 = await client.post(f"/api/v1/conversations/{conv.id}/alignment/analyze", headers=headers)
    assert r2.status_code == 403

    # Authorized member gets findings
    member_token = create_access_token(user_id=str(test_user.id), username=test_user.username)
    m_headers = {"Authorization": f"Bearer {member_token}"}
    r3 = await client.get(f"/api/v1/conversations/{conv.id}/ai-items", headers=m_headers)
    assert r3.status_code == 200
    assert len(r3.json()["findings"]) == 1


# --- Regression Test I ---
@pytest.mark.asyncio
async def test_i_concurrent_batch_processing_cannot_create_duplicate_jobs_or_findings(db_session, test_user, test_user_b):
    """I. Concurrent batch processing cannot create duplicate jobs or findings."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -20)

    # 1. Concurrent enqueue: unique message constraint prevents duplicate jobs
    q = AnalysisQueue(db_session)
    first = await q.enqueue(m.id, conv.id)
    second = await q.enqueue(m.id, conv.id)
    await db_session.commit()
    assert first is True
    assert second is False
    assert len(await get_jobs(db_session)) == 1

    # 2. Concurrent analysis detection calls
    res = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Tomorrow is ambiguous.",
                confidence=0.9,
                supporting_message_ids=[str(m.id)],
            )
        ],
    )

    async def slow_detect(*args, **kwargs):
        await asyncio.sleep(0.05)
        return res

    with use_ai_patch(AsyncMock(side_effect=slow_detect)):
        s1 = AlignmentService(db_session)
        s2 = AlignmentService(db_session)
        r1, r2 = await asyncio.gather(
            s1._detect_and_persist_batch(conv.id),
            s2._detect_and_persist_batch(conv.id),
        )

    # Exactly one finding created in DB
    assert await count_findings(db_session, conv) == 1
    total_new = len(r1[0]) + len(r2[0])
    assert total_new == 1


# --- Regression Test J ---
@pytest.mark.asyncio
async def test_j_receiver_initiated_clarification_and_confirmation_workflow(db_session, test_user, test_user_b):
    """J. The existing receiver-initiated clarification workflow and participant-confirmation rules continue to pass."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    await enqueue_msgs(db_session, conv, [m])

    res = AlignmentAnalysisResult(
        mismatch_detected=True,
        analyzed_message_ids=[str(m.id)],
        findings=[
            AlignmentFindingItem(
                mismatch_detected=True,
                category="deadlines",
                title="Vague Deadline",
                explanation="Tomorrow is ambiguous.",
                confidence=0.9,
                supporting_message_ids=[str(m.id)],
                clarification_question="What time tomorrow?",
            )
        ],
    )
    with use_ai_patch(AsyncMock(return_value=res)):
        batch, _, _ = await process_conversation_jobs(db_session, conv.id)

    finding = batch[0]
    service = AlignmentService(db_session)

    # Receiver asks for clarification
    updated_finding, msg, created = await service.request_clarification(conv.id, finding.id, test_user_b.id)
    await db_session.commit()
    assert created is True
    assert updated_finding.status == "clarifying"
    assert "clarification_request" in msg.msg_metadata.get("kind")

    # Idempotent second call
    _, msg2, created2 = await service.request_clarification(conv.id, finding.id, test_user_b.id)
    assert created2 is False
    assert msg.id == msg2.id

    # Participant confirms finding
    confirmed = await service.confirm_alignment_finding(conv.id, finding.id, test_user.id, comment="Confirmed at 4 PM")
    await db_session.commit()
    assert confirmed.status in ("awaiting_confirmation", "resolved")
