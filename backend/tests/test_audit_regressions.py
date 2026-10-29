"""Regression tests for defects found in the alignment-pipeline audit."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.analysis_job import MessageAnalysisJob
from app.providers.groq_provider import groq_provider
from app.services.analysis_queue import AnalysisQueue
from app.sockets import events
from tests.test_alignment_dedup import add_msg, make_conv
from tests.test_analysis_queue import file_db, jobs  # noqa: F401

IDS = {"11111111-1111-1111-1111-111111111111"}


def completion(payload) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


async def run_detect(payload):
    with patch.object(groq_provider, "_ensure_configured", return_value=None), patch.object(
        groq_provider, "_post_chat_completion", AsyncMock(return_value=completion(payload))
    ):
        return await groq_provider.detect_alignment(conversation_context=[], valid_message_ids=IDS, target_message_ids=list(IDS))


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"foo": "bar"}, {"findings": [], "analyzed_message_ids": ["not-a-real-id"]}])
async def test_malformed_alignment_reply_is_a_failure_not_a_clean_analysis(payload):
    assert await run_detect(payload) is None


@pytest.mark.asyncio
async def test_valid_empty_findings_with_real_coverage_is_a_genuine_no_issue():
    result = await run_detect({"findings": [], "analyzed_message_ids": list(IDS)})
    assert result is not None and result.findings == [] and result.analyzed_message_ids == list(IDS)


@pytest.mark.asyncio
async def test_enqueue_is_safe_under_a_concurrent_duplicate(db_session, test_user, test_user_b):
    conv = await make_conv(db_session, test_user, test_user_b)
    m = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    q = AnalysisQueue(db_session)
    # Simulate losing the check-then-insert race: the existence check says "none" but the row exists.
    assert await q.enqueue(m.id, conv.id) is True
    await db_session.commit()
    with patch.object(db_session, "execute", wraps=db_session.execute) as ex:
        real = db_session.execute

        class Empty:
            def scalar_one_or_none(self):
                return None

        calls = {"n": 0}

        async def first_empty(*a, **k):
            calls["n"] += 1
            return Empty() if calls["n"] == 1 else await real(*a, **k)

        ex.side_effect = first_empty
        assert await q.enqueue(m.id, conv.id) is False
    assert len(await jobs(db_session)) == 1
    # the session is still usable afterwards
    assert await q.enqueue(m.id, conv.id) is False


@pytest.mark.asyncio
async def test_socket_persistence_errors_do_not_leak_internals():
    emitted = []

    async def fake_emit(event, data, room=None):
        emitted.append((event, data))

    class Session(dict):
        pass

    secret = "sqlite3.OperationalError: no such table: secret_internal_table"
    with patch.object(events.sio, "get_session", AsyncMock(return_value={"user_id": "00000000-0000-0000-0000-000000000001"})), \
         patch.object(events.sio, "emit", fake_emit), \
         patch.object(events.ConversationService, "save_message", AsyncMock(side_effect=RuntimeError(secret))):
        await events.handle_message_send("sid", {
            "conversation_id": "00000000-0000-0000-0000-000000000002", "content": "hello", "client_id": "c1",
        })
    err = [d for e, d in emitted if e == "message:error"]
    assert err and err[0]["code"] == "PERSISTENCE_ERROR"
    assert "secret_internal_table" not in json.dumps(err[0])
    assert err[0]["client_id"] == "c1"


@pytest.mark.asyncio
async def test_failed_provider_jobs_get_one_more_attempt_but_only_when_recent(db_session, test_user, test_user_b):
    from datetime import timedelta
    from sqlalchemy import update
    from app.db.base import utc_now

    conv = await make_conv(db_session, test_user, test_user_b)
    recent = await add_msg(db_session, conv, test_user, "Submit it tomorrow", -5)
    old = await add_msg(db_session, conv, test_user, "Use that one", -4)
    q = AnalysisQueue(db_session)
    for m in (recent, old):
        await q.enqueue(m.id, conv.id)
    await db_session.commit()
    await db_session.execute(update(MessageAnalysisJob).values(status="failed", outcome="provider_failed", attempts=3))
    await db_session.execute(
        update(MessageAnalysisJob).where(MessageAnalysisJob.message_id == old.id).values(created_at=utc_now() - timedelta(days=3))
    )
    await db_session.commit()

    assert await q.revive_failed(conv.id) == 1
    by_msg = {j.message_id: j for j in await jobs(db_session)}
    await db_session.refresh(by_msg[recent.id])
    assert by_msg[recent.id].status == "pending" and by_msg[recent.id].attempts == 2  # one attempt left
    assert by_msg[old.id].status == "failed"
    assert await q.revive_failed(conv.id) == 0  # nothing left to revive; no loop


@pytest.mark.asyncio
async def test_concurrent_replay_of_one_client_id_creates_a_single_message_and_job(file_db):
    import asyncio
    from sqlalchemy import func, select
    from app.models.message import Message
    from app.schemas.message import MessageCreate
    from app.services.conversation_service import ConversationService

    factory, ann, ben = file_db
    async with factory() as db:
        conv = await make_conv(db, ann, ben)
        await db.commit()

    async def send(sender, client_id):
        async with factory() as db:
            saved = await ConversationService(db).save_message(
                conv.id, sender.id, MessageCreate(content="Send the invoice next week", client_id=client_id)
            )
            await AnalysisQueue(db).enqueue(saved.id, saved.conversation_id)
            await db.commit()
            return saved.id

    ids = await asyncio.gather(*[send(ann, "replay-1") for _ in range(8)])
    assert len(set(ids)) == 1

    # Another member using the same key is a different message, never resolved to Ann's.
    ben_id = await send(ben, "replay-1")
    assert ben_id != ids[0]

    async with factory() as db:
        msgs = (await db.execute(select(func.count()).select_from(Message).where(Message.client_id == "replay-1"))).scalar_one()
        njobs = (await db.execute(select(func.count()).select_from(MessageAnalysisJob))).scalar_one()
    assert msgs == 2 and njobs == 2
