"""
Tests for Continuous Conversation Understanding, Pre-Send Clarity,
Empty Message Blocking, and Two-Participant Shared Clarification Workflow.
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.conversation import Conversation, ConversationMember
from app.models.alignment import AlignmentFinding
from app.schemas.message import MessageCreate
from app.schemas.events import ClientSendMessagePayload
from app.services.spelling_engine import get_spelling_corrections
from app.core.config import settings

@pytest.mark.asyncio
async def test_empty_message_blocked_in_pydantic_schema():
    """Verify whitespace-only messages are blocked with validation error in schemas."""
    with pytest.raises(ValueError) as exc:
        MessageCreate(content="   ", message_type="text")
    assert "empty or contain only whitespace" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        ClientSendMessagePayload(conversation_id=uuid.uuid4(), content="  \t\n  ", message_type="text")
    assert "empty or contain only whitespace" in str(exc.value)

@pytest.mark.asyncio
async def test_legitimate_short_messages_allowed():
    """Verify legitimate short messages like OK, yes, no are allowed."""
    for valid_word in ["OK", "yes", "no", "Sure", "Fine"]:
        msg = MessageCreate(content=valid_word, message_type="text")
        assert msg.content == valid_word
        payload = ClientSendMessagePayload(conversation_id=uuid.uuid4(), content=valid_word, message_type="text")
        assert payload.content == valid_word

@pytest.mark.asyncio
async def test_pre_send_clarity_rules_in_local_engine():
    """Verify pre-send clarity assistance produces high-confidence suggestions with reasons."""
    cases = [
        ("submission tomorrow", "The submission is due tomorrow.", "The deadline is unclear."),
        ("tomorrow is submission", "The submission is due tomorrow.", "The deadline is unclear."),
        ("send the final version", "Please send the final version of the project report.", "Unclear document reference"),
        ("finish it by evening", "Please finish it by 5 PM today.", "Ambiguous deadline time"),
        ("deploy it after testing", "Deploy to production after automated testing passes.", "Unclear deployment target"),
    ]
    for raw, expected_corr, expected_reason in cases:
        corrections, corrected_text = get_spelling_corrections(raw)
        assert len(corrections) > 0, f"Expected correction for '{raw}'"
        assert corrections[0]["corrected"] == expected_corr
        assert corrections[0]["reason"] == expected_reason
        assert corrected_text == expected_corr

@pytest.mark.asyncio
async def test_local_spelling_names_slang_code_preservation():
    """Verify names, slang, code, and URLs are preserved without aggressive changes."""
    preserved = [
        "I like Anirudh music",
        "I am meeting Vijay in Chennai",
        "Check http://localhost:5173/chat",
        "const status = await getStatus()",
        "Hey bro, that beat was lit!",
    ]
    for text in preserved:
        corrections, corrected_text = get_spelling_corrections(text)
        assert corrections == [], f"Expected zero corrections for clean text: {text}"
        assert corrected_text is None

@pytest.mark.asyncio
async def test_two_participant_clarification_comment(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_user_b: User,
    auth_headers: dict,
    auth_headers_b: dict,
):
    """
    Verify shared clarification workflow:
    1. Alignment finding exists in conversation.
    2. Participant A submits clarification response.
    3. Finding persists response in confirmations.
    4. Participant B views persisted response.
    5. Participant B confirms, transitioning issue to resolved.
    """
    # 1. Create a 1-on-1 conversation
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    mem1 = ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member")
    mem2 = ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member")
    db_session.add_all([mem1, mem2])

    # 2. Add an alignment finding
    finding = AlignmentFinding(
        conversation_id=conv.id,
        mismatch_detected=True,
        category="deadlines",
        title="Ambiguous Submission Deadline",
        severity="medium",
        status="detected",
        explanation="Submission time is unstated in chat.",
        confidence=0.92,
        clarification_question="What is the submission deadline, including expected time?",
        supporting_message_ids=[],
    )
    db_session.add(finding)
    await db_session.commit()
    await db_session.refresh(finding)

    # 3. Participant A clarifies with comment
    res_a = await client.post(
        f"/api/v1/conversations/{conv.id}/alignment/{finding.id}/confirm",
        headers=auth_headers,
        json={"comment": "The report must be uploaded by 5 PM IST tomorrow."},
    )
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert len(data_a["confirmations"]) == 1
    assert data_a["confirmations"][0]["username"] == test_user.username
    assert data_a["confirmations"][0]["comment"] == "The report must be uploaded by 5 PM IST tomorrow."
    assert data_a["status"] == "awaiting_confirmation"

    # 4. Participant B checks conversation AI items (reconnecting / late-arriving verification)
    res_items = await client.get(
        f"/api/v1/conversations/{conv.id}/ai-items",
        headers=auth_headers_b,
    )
    assert res_items.status_code == 200
    items_data = res_items.json()
    assert len(items_data["findings"]) == 1
    found_item = items_data["findings"][0]
    assert found_item["confirmations"][0]["comment"] == "The report must be uploaded by 5 PM IST tomorrow."

    # 5. Participant B confirms clarification
    res_b = await client.post(
        f"/api/v1/conversations/{conv.id}/alignment/{finding.id}/confirm",
        headers=auth_headers_b,
        json={"comment": "Confirmed, 5 PM IST works."},
    )
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert len(data_b["confirmations"]) == 2
    assert data_b["status"] == "resolved"
    assert data_b["resolved_at"] is not None

@pytest.mark.asyncio
async def test_unauthorized_user_cannot_access_or_confirm_finding(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_user_b: User,
    auth_headers: dict,
):
    """Verify security isolation: user outside conversation cannot access or confirm finding."""
    # Conversation only has user_b
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.commit()

    mem2 = ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member")
    db_session.add(mem2)

    finding = AlignmentFinding(
        conversation_id=conv.id,
        mismatch_detected=True,
        category="deadlines",
        title="Private Issue",
        explanation="Private issue explanation",
        status="detected",
        confidence=0.85,
    )
    db_session.add(finding)
    await db_session.commit()

    # test_user (Alice) is not a member of conv
    res = await client.post(
        f"/api/v1/conversations/{conv.id}/alignment/{finding.id}/confirm",
        headers=auth_headers,
        json={"comment": "Hacking confirmation"},
    )
    assert res.status_code == 403
