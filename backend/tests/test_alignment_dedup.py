"""Regression tests: resolved alignment findings must not be re-created by Check Alignment,
plus the receiver-initiated clarification request flow."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings
from app.db.base import utc_now
from app.models.alignment import AlignmentFinding
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User
from app.providers.nvidia_provider import nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult
from app.services.alignment_service import AlignmentService, _last_analysis_time


async def make_conv(db: AsyncSession, a: User, b: User) -> Conversation:
    conv = Conversation(
        is_group=False,
        direct_user_low_id=min(a.id, b.id),
        direct_user_high_id=max(a.id, b.id),
    )
    db.add(conv)
    await db.commit()
    db.add_all([
        ConversationMember(conversation_id=conv.id, user_id=a.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=b.id, role="member"),
    ])
    await db.commit()
    return conv


async def add_msg(db: AsyncSession, conv: Conversation, sender: User, text: str, offset_s: int = 0) -> Message:
    m = Message(
        conversation_id=conv.id,
        sender_id=sender.id,
        content=text,
        message_type="text",
        created_at=utc_now() + timedelta(seconds=offset_s),
    )
    db.add(m)
    await db.commit()
    return m


def result(msg_ids, title="Unclear Submission Target", category="unclear_references", question="Which assignment?"):
    return AlignmentAnalysisResult(
        mismatch_detected=True,
        category=category,
        severity="medium",
        title=title,
        explanation="Missing detail.",
        confidence=0.9,
        supporting_message_ids=[str(i) for i in msg_ids],
        clarification_question=question,
    )


def patched(mock):
    return (
        patch.object(Settings, "is_provider_configured", return_value=True),
        patch.object(nvidia_provider, "_ensure_configured", return_value=None),
        patch.object(nvidia_provider, "detect_alignment", mock),
    )


async def resolve(db, service, conv, finding_id, user):
    await service.confirm_alignment_finding(conv.id, finding_id, user.id, comment="The database assignment.")
    await db.commit()
    await service.resolve_alignment_finding(conv.id, finding_id, user.id, evidence="Database assignment")
    await db.commit()


async def count_findings(db, conv) -> int:
    r = await db.execute(select(func.count()).select_from(AlignmentFinding).where(AlignmentFinding.conversation_id == conv.id))
    return r.scalar_one()


async def check(db, conv, user):
    service = AlignmentService(db)
    f = await service.trigger_alignment_analysis(conv.id, user.id)
    return f, service.last_was_new


@pytest.mark.asyncio
async def test_resolved_finding_not_recreated_on_repeated_checks(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, is_new = await check(db_session, conv, test_user_b)
        assert f is not None and is_new
        await resolve(db_session, AlignmentService(db_session), conv, f.id, test_user)

        for _ in range(3):  # repeated clicks / fresh service instances = refresh + reconnect
            again, is_new = await check(db_session, conv, test_user_b)
            assert again is None and not is_new
    assert await count_findings(db_session, conv) == 1
    row = (await db_session.execute(select(AlignmentFinding))).scalar_one()
    assert row.status == "resolved"
    assert row.confirmations and row.status_history  # history preserved


@pytest.mark.asyncio
async def test_established_context_sent_to_ai(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)
        await resolve(db_session, AlignmentService(db_session), conv, f.id, test_user)
        await check(db_session, conv, test_user_b)
    established = mock.call_args.kwargs["established_context"]
    assert established and "Database assignment" in established[0]["confirmed_answer"]


@pytest.mark.asyncio
async def test_same_issue_with_different_wording_is_recognized(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    mock = AsyncMock(side_effect=[
        result([m1.id]),
        result([m1.id], title="Ambiguous pronoun reference", category="ambiguity", question="What does 'it' mean?"),
    ])
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)
        await resolve(db_session, AlignmentService(db_session), conv, f.id, test_user)
        again, is_new = await check(db_session, conv, test_user_b)
    assert again is None and not is_new
    assert await count_findings(db_session, conv) == 1


@pytest.mark.asyncio
async def test_repeated_check_alignment_with_different_category_label_does_not_duplicate_active_finding(db_session, test_user, test_user_b):
    """Regression: an ACTIVE (not yet resolved) finding must not be duplicated just because a
    later Check Alignment call re-labels the same message under a different category/title.
    Evidence overlap alone is enough to recognize it as the same issue."""
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Make this as reminder for our project deadline after the person is given.", -30)
    mock = AsyncMock(side_effect=[
        result([m1.id], title="Missing reminder details", category="deadlines", question="What is the task and deadline?"),
        result([m1.id], title="Unclear dependency on the person", category="unclear_references", question="Who is 'the person'?"),
    ])
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, is_new = await check(db_session, conv, test_user_b)
        assert f is not None and is_new
        again, is_new_again = await check(db_session, conv, test_user_b)
    assert again is not None and again.id == f.id and not is_new_again
    assert await count_findings(db_session, conv) == 1


@pytest.mark.asyncio
async def test_concurrent_checks_create_one_finding(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.05)
        return result([m1.id])

    p1, p2, p3 = patched(slow)
    with p1, p2, p3:
        s1, s2 = AlignmentService(db_session), AlignmentService(db_session)
        r1, r2 = await asyncio.gather(s1._detect_and_persist(conv.id), s2._detect_and_persist(conv.id))
    assert r1 is not None and r2 is not None and r1.id == r2.id
    assert [s1.last_was_new, s2.last_was_new].count(True) == 1
    assert await count_findings(db_session, conv) == 1


@pytest.mark.asyncio
async def test_resolved_and_unrelated_new_issue_coexist(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -60)
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)
        await resolve(db_session, AlignmentService(db_session), conv, f.id, test_user)
        m2 = await add_msg(db_session, conv, test_user, "Submit the project by 5.", 60)
        mock.return_value = result([m2.id], title="Unclear deadline time", category="deadlines", question="5 AM or PM?")
        new, is_new = await check(db_session, conv, test_user_b)
    assert new is not None and is_new and new.title == "Unclear deadline time"
    statuses = {r.title: r.status for r in (await db_session.execute(select(AlignmentFinding))).scalars()}
    assert statuses["Unclear Submission Target"] == "resolved"
    assert statuses["Unclear deadline time"] == "detected"


@pytest.mark.asyncio
async def test_new_ambiguity_related_to_previous_topic_is_detected(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -60)
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)
        await resolve(db_session, AlignmentService(db_session), conv, f.id, test_user)
        m2 = await add_msg(db_session, conv, test_user, "Submit the database one by Friday, same format.", 60)
        # Cites the old message too, but is a different issue (format) raised in a newer message.
        mock.return_value = result([m1.id, m2.id], title="Unspecified output format", category="scope", question="Which format?")
        new, is_new = await check(db_session, conv, test_user_b)
    assert new is not None and is_new
    assert await count_findings(db_session, conv) == 2


@pytest.mark.asyncio
async def test_awaiting_confirmation_is_not_treated_as_resolved(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)
        service = AlignmentService(db_session)
        await service.confirm_alignment_finding(conv.id, f.id, test_user.id, comment="The database assignment.")
        await db_session.commit()
        row = await db_session.get(AlignmentFinding, f.id)
        assert row.status == "awaiting_confirmation"
        again, is_new = await check(db_session, conv, test_user_b)
    assert again is not None and again.id == f.id and not is_new  # still surfaced, not recreated
    assert again.status == "awaiting_confirmation"
    assert await count_findings(db_session, conv) == 1


@pytest.mark.asyncio
async def test_non_member_cannot_access_findings(client, db_session, test_user, test_user_b):
    from app.core.security import create_access_token

    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)

    outsider = User(email="eve@example.com", username="eve", username_normalized="eve", display_name="Eve", is_active=True)
    db_session.add(outsider)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id=str(outsider.id), username='eve')}"}
    base = f"/api/v1/conversations/{conv.id}"
    for method, url in [
        ("post", f"{base}/alignment/analyze"),
        ("get", f"{base}/ai-items"),
        ("post", f"{base}/alignment/{f.id}/confirm"),
        ("post", f"{base}/alignment/{f.id}/resolve"),
        ("post", f"{base}/alignment/{f.id}/request-clarification"),
    ]:
        resp = await getattr(client, method)(url, headers=headers)
        assert resp.status_code == 403, (url, resp.status_code)


@pytest.mark.asyncio
async def test_receiver_requests_clarification_flow(client, db_session, test_user, test_user_b, auth_headers, auth_headers_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    m1 = await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)  # Alice is the author
    mock = AsyncMock(return_value=result([m1.id]))
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, _ = await check(db_session, conv, test_user_b)

    url = f"/api/v1/conversations/{conv.id}/alignment/{f.id}/request-clarification"
    # The author cannot request clarification of their own message
    assert (await client.post(url, headers=auth_headers)).status_code == 400

    r = await client.post(url, headers=auth_headers_b)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "clarifying" and body["clarification_request_message_id"]

    # Idempotent: a replay does not create a second request message
    assert (await client.post(url, headers=auth_headers_b)).status_code == 200
    msgs = (await db_session.execute(select(Message).where(Message.message_type == "ai_alignment"))).scalars().all()
    assert len(msgs) == 1
    meta = msgs[0].msg_metadata
    assert meta["kind"] == "clarification_request"
    assert meta["finding_id"] == str(f.id) and meta["original_message_id"] == str(m1.id)
    assert msgs[0].conversation_id == conv.id and msgs[0].sender_id == test_user_b.id
    assert "Submit it tomorrow." in msgs[0].content  # original message left unchanged, quoted in the request
    original = await db_session.get(Message, m1.id)
    assert original.content == "Submit it tomorrow."


@pytest.mark.asyncio
async def test_provider_failure_returns_none_without_finding(db_session, test_user, test_user_b):
    _last_analysis_time.clear()
    conv = await make_conv(db_session, test_user, test_user_b)
    await add_msg(db_session, conv, test_user, "Submit it tomorrow.", -30)
    mock = AsyncMock(return_value=None)
    p1, p2, p3 = patched(mock)
    with p1, p2, p3:
        f, is_new = await check(db_session, conv, test_user_b)
    assert f is None and not is_new
    assert await count_findings(db_session, conv) == 0
