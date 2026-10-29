"""Automated tests for NVIDIA NIM AI alignment analysis and finding persistence."""

import uuid
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings, settings
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User
from app.providers.nvidia_provider import nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult
from app.services.alignment_service import AlignmentService, _last_analysis_time


@pytest.mark.asyncio
async def test_alignment_analysis_grounded_evidence_and_persistence(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    _last_analysis_time.clear()

    # 1. Setup conversation and messages
    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()

    msg1 = Message(conversation_id=conv.id, sender_id=test_user.id, content="Let's ship the core feature by Friday.", message_type="text")
    msg2 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="I assumed we were including the full billing system by Friday.", message_type="text")
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    valid_id_1 = str(msg1.id)
    fake_id = str(uuid.uuid4())

    mock_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        category="scope",
        severity="medium",
        title="Scope Misalignment on Release Content",
        explanation="One person considers the release core features only, while the other expects full billing included.",
        confidence=0.88,
        supporting_message_ids=[valid_id_1, fake_id],  # Includes fake ID to test grounding
        clarification_question="Can we confirm whether billing is in scope for this Friday's release?",
        suggested_rewrite="Should we ship core features first on Friday, and deploy billing in the next cycle?",
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_alignment", return_value=mock_result):
        alignment_service = AlignmentService(db_session)
        finding = await alignment_service.analyze_conversation(conv.id, triggering_message_id=msg2.id)

        assert finding is not None
        assert finding.mismatch_detected
        assert finding.category == "scope"
        assert finding.severity == "medium"
        assert finding.title == "Scope Misalignment on Release Content"
        assert finding.confidence == 0.88
        assert finding.suggested_rewrite is not None
        # Verify fake ID was filtered out by grounding check
        assert fake_id not in finding.supporting_message_ids
        assert valid_id_1 in finding.supporting_message_ids

    # 2. Cooldown check: second immediate call must be throttled
    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "detect_alignment") as mock_second_call:
        finding_cooldown = await alignment_service.analyze_conversation(conv.id, triggering_message_id=msg2.id)
        assert finding_cooldown is None
        mock_second_call.assert_not_called()


@pytest.mark.asyncio
async def test_alignment_suppresses_clear_or_aligned_conversations(
    db_session: AsyncSession, test_user: User, test_user_b: User
):
    _last_analysis_time.clear()

    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()

    msg1 = Message(conversation_id=conv.id, sender_id=test_user.id, content="Sounds good, see you tomorrow.")
    msg2 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="Agreed, talk tomorrow.")
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    # Mismatch is False
    aligned_result = AlignmentAnalysisResult(
        mismatch_detected=False,
        explanation="Both participants are in agreement regarding scheduling.",
        confidence=0.95,
        supporting_message_ids=[],
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_alignment", return_value=aligned_result):
        alignment_service = AlignmentService(db_session)
        finding = await alignment_service.analyze_conversation(conv.id)
        assert finding is None


@pytest.mark.asyncio
async def test_ambiguous_instruction_triggers_finding_with_rewrite(
    db_session: AsyncSession, test_user: User, test_user_b: User
):
    _last_analysis_time.clear()

    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()

    msg1 = Message(conversation_id=conv.id, sender_id=test_user.id, content="I will send the final version tomorrow.", message_type="text")
    msg2 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="Okay.", message_type="text")
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    mock_ambiguity = AlignmentAnalysisResult(
        mismatch_detected=True,
        category="ambiguity",
        severity="medium",
        title="Ambiguous Deadline and Document Version",
        explanation="The phrase 'tomorrow' lacks a time/timezone, and 'final version' does not specify the draft.",
        confidence=0.91,
        supporting_message_ids=[str(msg1.id)],
        clarification_question="Which specific time tomorrow and which draft version should we align on?",
        suggested_rewrite="I will send draft v2.4 tomorrow by 3 PM EST.",
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_alignment", return_value=mock_ambiguity):
        alignment_service = AlignmentService(db_session)
        finding = await alignment_service.analyze_conversation(conv.id, triggering_message_id=msg2.id)

        assert finding is not None
        assert finding.category == "ambiguity"
        assert finding.suggested_rewrite == "I will send draft v2.4 tomorrow by 3 PM EST."
        assert str(msg1.id) in finding.supporting_message_ids


@pytest.mark.asyncio
async def test_malformed_ai_output_handled_safely(
    db_session: AsyncSession, test_user: User, test_user_b: User
):
    _last_analysis_time.clear()

    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()

    msg1 = Message(conversation_id=conv.id, sender_id=test_user.id, content="Let's do it like before.", message_type="text")
    db_session.add(msg1)
    await db_session.commit()

    # Model raises unexpected exception or parsing failure
    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_alignment", side_effect=Exception("API connection timeout")):
        alignment_service = AlignmentService(db_session)
        # Must not raise; must handle safely and return None
        finding = await alignment_service.analyze_conversation(conv.id)
        assert finding is None


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_read_findings(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers_b: dict[str, str], db_session: AsyncSession
):
    # Conversation between test_user and another user, not test_user_b
    other_user = User(
        email="unrelated@example.com",
        username="unrelated_user",
        username_normalized="unrelated_user",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()

    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, other_user.id), direct_user_high_id=max(test_user.id, other_user.id))
    db_session.add(conv)
    await db_session.commit()

    # test_user_b attempts to fetch AI items for a conversation they do not belong to
    resp = await client.get(f"/api/v1/conversations/{conv.id}/ai-items", headers=auth_headers_b)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_explicit_trigger_alignment_endpoint(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    conv = Conversation(is_group=False, direct_user_low_id=min(test_user.id, test_user_b.id), direct_user_high_id=max(test_user.id, test_user_b.id))
    db_session.add(conv)
    await db_session.commit()
    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member"),
    ])
    await db_session.commit()

    msg1 = Message(conversation_id=conv.id, sender_id=test_user.id, content="We will launch soon.", message_type="text")
    db_session.add(msg1)
    await db_session.commit()

    mock_result = AlignmentAnalysisResult(
        mismatch_detected=True,
        category="ambiguity",
        severity="low",
        title="Vague Launch Timeframe",
        explanation="The word 'soon' leaves the launch date undefined.",
        confidence=0.85,
        supporting_message_ids=[str(msg1.id)],
        clarification_question="Could we specify an exact target date for the launch?",
        suggested_rewrite="We will launch on November 1st.",
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_alignment", return_value=mock_result):

        resp = await client.post(
            f"/api/v1/conversations/{conv.id}/alignment/analyze",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["category"] == "ambiguity"
        assert data["suggested_rewrite"] == "We will launch on November 1st."
