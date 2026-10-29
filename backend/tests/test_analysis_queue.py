"""Durable per-message analysis queue, casual-chat false positives, group targeting,
Socket.IO duplicate/replay handling. AI providers are MOCKED in this file (no live calls)."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from app.core.config import Settings
from app.core.security import create_access_token
from app.db.base import utc_now
from app.models.alignment import AlignmentFinding
from app.models.analysis_job import MessageAnalysisJob
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User
from app.providers.groq_provider import groq_provider
from app.providers.nvidia_provider import nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult
from app.services import ai_decision_engine
from app.services.ai_decision_engine import AIDecisionEngine
from app.services.alignment_service import _last_analysis_time
from app.services.analysis_queue import AnalysisQueue, is_casual_acknowledgement, process_conversation_jobs
from app.sockets.events import handle_message_send
from app.sockets.server import sio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db.base import Base
from tests.test_alignment_dedup import add_msg, make_conv, result


@pytest_asyncio.fixture
async def file_db(tmp_path):
    """File-backed SQLite so multiple independent sessions (workers) share one database."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'q.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with factory() as setup:
        a = await make_user(setup, "ann")
        b = await make_user(setup, "ben")
    yield factory, a, b
    await engine.dispose()


def ai(mock):
    return (
        patch.object(Settings, "is_provider_configured", return_value=True),
        patch.object(nvidia_provider, "_ensure_configured", return_value=None),
        patch.object(nvidia_provider, "detect_alignment", mock),
        patch.object(groq_provider, "detect_alignment", AsyncMock(return_value=None)),
    )


class use_ai:
    def __init__(self, mock):
        self.patches = ai(mock)

    def __enter__(self):
        for p in self.patches:
            p.start()

    def __exit__(self, *a):
        for p in self.patches:
            p.stop()


async def enqueue_all(db, conv, msgs):
    q = AnalysisQueue(db)
    for m in msgs:
        await q.enqueue(m.id, conv.id)
    await db.commit()


async def jobs(db):
    return (await db.execute(select(MessageAnalysisJob).order_by(MessageAnalysisJob.created_at))).scalars().all()


async def n_findings(db, conv):
    return (await db.execute(select(func.count()).select_from(AlignmentFinding).where(AlignmentFinding.conversation_id == conv.id))).scalar_one()


# ---------------- casual messages / false positives ----------------

@pytest.mark.parametrize("text", ["Hi", "OK", "Yes", "No", "Thanks", "LOL", "Sounds good", "ok!", "  Thanks. "])
def test_casual_acknowledgements_recognized(text):
    assert is_casual_acknowledgement(text)


@pytest.mark.parametrize("text", ["Submit it tomorrow", "Let's meet at 5", "Use that one", "Make it simple", "ok but when?"])
def test_short_but_meaningful_messages_not_exempt(text):
    assert not is_casual_acknowledgement(text)


@pytest.mark.asyncio
async def test_casual_messages_get_durable_outcome_without_ai_or_finding(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    msgs = [await add_msg(db_session, conv, test_user, t, i) for i, t in enumerate(["Hi", "OK", "Yes", "No", "Thanks", "LOL", "Sounds good"])]
    await enqueue_all(db_session, conv, msgs)
    mock = AsyncMock(return_value=result([msgs[0].id]))
    with use_ai(mock):
        finding, retry, processed = await process_conversation_jobs(db_session, conv.id)
    assert processed and finding is None and retry is None
    mock.assert_not_called()
    assert {j.status for j in await jobs(db_session)} == {"done"}
    assert {j.outcome for j in await jobs(db_session)} == {"skipped_casual"}
    assert await n_findings(db_session, conv) == 0


@pytest.mark.asyncio
async def test_ambiguous_message_is_analyzed_and_flagged(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    await enqueue_all(db_session, conv, [m])
    mock = AsyncMock(return_value=result([m.id]))
    with use_ai(mock):
        finding, _, _ = await process_conversation_jobs(db_session, conv.id)
    assert finding is not None and finding.status == "detected"
    assert [j.outcome for j in await jobs(db_session)] == ["finding_created"]


@pytest.mark.asyncio
async def test_clear_message_with_no_mismatch_gets_no_finding(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "I will send the completed assignment at 4 PM tomorrow.", -5)
    await enqueue_all(db_session, conv, [m])
    clear = AlignmentAnalysisResult(mismatch_detected=False, explanation="", confidence=0.9, supporting_message_ids=[])
    with use_ai(AsyncMock(return_value=clear)):
        finding, _, _ = await process_conversation_jobs(db_session, conv.id)
    assert finding is None and await n_findings(db_session, conv) == 0
    assert [(j.status, j.outcome) for j in await jobs(db_session)] == [("done", "no_issue")]


# ---------------- queue durability ----------------

@pytest.mark.asyncio
async def test_duplicate_enqueue_is_idempotent(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    q = AnalysisQueue(db_session)
    assert await q.enqueue(m.id, conv.id) is True
    await db_session.commit()
    assert await q.enqueue(m.id, conv.id) is False
    assert len(await jobs(db_session)) == 1


@pytest.mark.asyncio
async def test_rapid_messages_in_debounce_window_all_get_outcomes(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    msgs = [await add_msg(db_session, conv, test_user, t, i) for i, t in enumerate(["Submit it tomorrow", "Use that one", "Make it simple"])]
    await enqueue_all(db_session, conv, msgs)
    mock = AsyncMock(return_value=result([msgs[0].id]))
    with use_ai(mock):
        await process_conversation_jobs(db_session, conv.id)
    js = await jobs(db_session)
    assert len(js) == 3 and {j.status for j in js} == {"done"}  # none dropped
    assert mock.await_count == 1  # batched into one analysis


@pytest.mark.asyncio
async def test_cooldown_does_not_suppress_later_message_analysis(db_session, test_user, test_user_b):
    import time
    conv = await make_conv(db_session, test_user, test_user_b)
    _last_analysis_time[conv.id] = time.time()  # a finding "just" fired: cooldown active
    m = await add_msg(db_session, conv, test_user, "Send the final version", -5)
    await enqueue_all(db_session, conv, [m])
    mock = AsyncMock(return_value=result([m.id], title="Which version", category="scope"))
    with use_ai(mock):
        finding, _, _ = await process_conversation_jobs(db_session, conv.id)
    mock.assert_awaited_once()
    assert finding is not None
    _last_analysis_time.clear()


@pytest.mark.asyncio
async def test_replayed_analysis_trigger_does_not_reanalyze_or_duplicate(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    await enqueue_all(db_session, conv, [m])
    mock = AsyncMock(return_value=result([m.id]))
    with use_ai(mock):
        await process_conversation_jobs(db_session, conv.id)
        again = await process_conversation_jobs(db_session, conv.id)  # duplicate trigger / replay
        await enqueue_all(db_session, conv, [m])                     # duplicate delivery event
        again2 = await process_conversation_jobs(db_session, conv.id)
    assert again == (None, None, False) and again2 == (None, None, False)
    assert mock.await_count == 1 and await n_findings(db_session, conv) == 1


@pytest.mark.asyncio
async def test_provider_failure_is_not_success_retries_bounded_and_recovers_without_duplicates(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    await enqueue_all(db_session, conv, [m])

    async def make_due():
        await db_session.execute(update(MessageAnalysisJob).values(next_attempt_at=utc_now() - timedelta(seconds=1)))
        await db_session.commit()

    failing = AsyncMock(return_value=None)
    with use_ai(failing):
        _, delay, _ = await process_conversation_jobs(db_session, conv.id)
        job = (await jobs(db_session))[0]
        assert job.status == "pending" and job.attempts == 1 and delay is not None  # not marked checked
        await make_due()
        await process_conversation_jobs(db_session, conv.id)
        # not yet due -> not claimed again (backoff respected)
        assert await process_conversation_jobs(db_session, conv.id) == (None, None, False)
        await make_due()
        await process_conversation_jobs(db_session, conv.id)
    job = (await jobs(db_session))[0]
    assert job.status == "failed" and job.attempts == 3 and job.outcome == "provider_failed"
    assert await n_findings(db_session, conv) == 0

    # Operator/recovery re-queues; provider is back: exactly one finding.
    await db_session.execute(update(MessageAnalysisJob).values(status="pending", attempts=0, next_attempt_at=utc_now()))
    await db_session.commit()
    ok = AsyncMock(return_value=result([m.id]))
    with use_ai(ok):
        await process_conversation_jobs(db_session, conv.id)
        await db_session.execute(update(MessageAnalysisJob).values(status="pending"))
        await db_session.commit()
        await process_conversation_jobs(db_session, conv.id)  # replayed after success
    assert await n_findings(db_session, conv) == 1


@pytest.mark.asyncio
async def test_unconfigured_ai_is_skipped_not_done(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    await enqueue_all(db_session, conv, [m])
    with patch.object(Settings, "is_provider_configured", return_value=False):
        await process_conversation_jobs(db_session, conv.id)
    assert [(j.status, j.outcome) for j in await jobs(db_session)] == [("skipped", "ai_not_configured")]


@pytest.mark.asyncio
async def test_restart_recovers_pending_and_stale_processing_jobs(file_db):
    factory, test_user, test_user_b = file_db
    db_session = factory()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -10)
    m2 = await add_msg(db_session, conv, test_user, "Use that one", -5)
    await enqueue_all(db_session, conv, [m1, m2])
    # m1's worker died mid-processing long ago
    await db_session.execute(
        update(MessageAnalysisJob)
        .where(MessageAnalysisJob.message_id == m1.id)
        .values(status="processing", claimed_at=utc_now() - timedelta(hours=1), attempts=1)
    )
    await db_session.commit()

    mock = AsyncMock(return_value=result([m1.id]))
    with use_ai(mock), patch.object(ai_decision_engine, "AsyncSessionLocal", factory), \
            patch.object(sio, "emit", new_callable=AsyncMock) as emit:
        await AIDecisionEngine.recover_pending()  # what the lifespan runs at startup
    async with factory() as check:
        assert {j.status for j in await jobs(check)} == {"done"}
        assert await n_findings(check, conv) == 1
    assert [c.args[0] for c in emit.call_args_list].count("ai:alignment") == 1


@pytest.mark.asyncio
async def test_concurrent_workers_process_a_message_once(file_db):
    factory, test_user, test_user_b = file_db
    db_session = factory()
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    await enqueue_all(db_session, conv, [m])

    async def slow(*a, **k):
        await asyncio.sleep(0.05)
        return result([m.id])

    mock = AsyncMock(side_effect=slow)
    with use_ai(mock):
        async def worker():
            async with factory() as s:
                return await process_conversation_jobs(s, conv.id)

        r = await asyncio.gather(worker(), worker())
    assert mock.await_count == 1
    assert sorted(x[2] for x in r) == [False, True]  # exactly one worker won the claim
    async with factory() as check:
        assert await n_findings(check, conv) == 1
        assert [j.status for j in await jobs(check)] == ["done"]


# ---------------- Socket.IO delivery ----------------

@pytest.mark.asyncio
async def test_duplicate_message_send_creates_one_message_and_one_job(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    payload = {"conversation_id": str(conv.id), "content": "Submit it tomorrow", "message_type": "text", "client_id": "cid-1"}
    with patch.object(sio, "get_session", return_value={"user_id": str(test_user.id), "username": "alice"}), \
            patch.object(sio, "emit", new_callable=AsyncMock) as emit, \
            patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
            patch("app.sockets.events.schedule_ai_pipeline"):
        await handle_message_send("sid", payload)
        await handle_message_send("sid", payload)  # replayed event after reconnect
    msgs = (await db_session.execute(select(Message).where(Message.conversation_id == conv.id))).scalars().all()
    assert len(msgs) == 1
    assert len(await jobs(db_session)) == 1
    # events only ever target this conversation's room (plus the sender sid for ack)
    rooms = {c.kwargs.get("room") for c in emit.call_args_list}
    assert rooms <= {f"conversation:{conv.id}", "sid"}


@pytest.mark.asyncio
async def test_empty_and_whitespace_messages_still_rejected(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    with patch.object(sio, "get_session", return_value={"user_id": str(test_user.id), "username": "alice"}), \
            patch.object(sio, "emit", new_callable=AsyncMock) as emit, \
            patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
            patch("app.sockets.events.schedule_ai_pipeline"):
        for content in ["", "   "]:
            await handle_message_send("sid", {"conversation_id": str(conv.id), "content": content, "message_type": "text"})
    assert len(await jobs(db_session)) == 0
    assert all(c.args[0] == "message:error" for c in emit.call_args_list)


# ---------------- group chats ----------------

async def make_group(db, creator, others, title="Team"):
    conv = Conversation(is_group=True, title=title)
    db.add(conv)
    await db.commit()
    db.add_all([ConversationMember(conversation_id=conv.id, user_id=u.id, role="member") for u in [creator, *others]])
    await db.commit()
    return conv


async def make_user(db, name):
    u = User(email=f"{name}@example.com", username=name, username_normalized=name, display_name=name, is_active=True)
    db.add(u)
    await db.commit()
    return u


def headers(u):
    return {"Authorization": f"Bearer {create_access_token(user_id=str(u.id), username=u.username)}"}


@pytest.mark.asyncio
async def test_group_findings_isolated_and_clarification_targets_only_members(client, db_session, test_user, test_user_b):
    carol = await make_user(db_session, "carol")
    dave = await make_user(db_session, "dave")  # member of an unrelated group only
    g1 = await make_group(db_session, test_user, [test_user_b, carol], "G1")
    g2 = await make_group(db_session, dave, [], "G2")
    m1 = await add_msg(db_session, g1, test_user, "Submit it tomorrow", -5)
    m2 = await add_msg(db_session, g2, dave, "Make it simple", -5)
    await enqueue_all(db_session, g1, [m1])
    await enqueue_all(db_session, g2, [m2])
    with use_ai(AsyncMock(side_effect=lambda **kw: result([next(iter(kw["valid_message_ids"]))]))):
        f1, _, _ = await process_conversation_jobs(db_session, g1.id)
        f2, _, _ = await process_conversation_jobs(db_session, g2.id)
    assert f1.conversation_id == g1.id and f2.conversation_id == g2.id

    # Dave (other group) can neither read G1's findings nor act on them
    base = f"/api/v1/conversations/{g1.id}"
    assert (await client.get(f"{base}/ai-items", headers=headers(dave))).status_code == 403
    assert (await client.post(f"{base}/alignment/{f1.id}/request-clarification", headers=headers(dave))).status_code == 403
    # A real G1 member cannot use G1's finding id through G2's URL (client-supplied conversation id is verified)
    assert (await client.post(f"/api/v1/conversations/{g2.id}/alignment/{f1.id}/request-clarification", headers=headers(dave))).status_code == 404

    # Bob (member, not the author) requests clarification; events go only to G1's room
    with patch.object(sio, "emit", new_callable=AsyncMock) as emit:
        r = await client.post(f"{base}/alignment/{f1.id}/request-clarification", headers=headers(test_user_b))
        assert r.status_code == 200
        # replayed click: no second message/event
        assert (await client.post(f"{base}/alignment/{f1.id}/request-clarification", headers=headers(test_user_b))).status_code == 200
    assert {c.kwargs["room"] for c in emit.call_args_list} == {f"conversation:{g1.id}"}
    assert [c.args[0] for c in emit.call_args_list] == ["message:new", "ai:alignment_update"]
    requests = (await db_session.execute(select(Message).where(Message.message_type == "ai_alignment"))).scalars().all()
    assert len(requests) == 1 and requests[0].conversation_id == g1.id

    # Reload/reconnect by two members: persisted, no duplicates, no leakage of G2's finding
    for u in (test_user, carol):
        for _ in range(2):
            items = (await client.get(f"{base}/ai-items", headers=headers(u))).json()
            assert [f["id"] for f in items["findings"]] == [str(f1.id)]
    assert (await client.get(f"/api/v1/conversations/{g2.id}/ai-items", headers=headers(test_user))).status_code == 403
