"""Tests for AI alignment lifecycle (detected -> clarifying -> awaiting_confirmation -> resolved),
casual acknowledgment protection, mutual confirmations, and recommendation dismissal.
"""

from unittest.mock import patch
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings
from app.models.alignment import AlignmentFinding
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.recommendation import RecommendationItem
from app.models.user import User
from app.providers.nvidia_provider import nvidia_provider
from app.schemas.ai import AlignmentAnalysisResult, ResolutionEvaluationResult
from app.services.alignment_service import AlignmentService, _last_analysis_time
from app.services.recommendation_service import RecommendationService


@pytest.mark.asyncio
async def test_alignment_lifecycle_evidence_resolution_and_casual_ack_protection(
    db_session: AsyncSession, test_user: User, test_user_b: User
):
    """
    Verify:
    1. Ambiguous message triggers finding in 'detected' status.
    2. Casual acknowledgment ('ok', 'cool') DOES NOT resolve; transitions to 'clarifying'.
    3. Factual concrete resolution evidence transitions to 'awaiting_confirmation'.
    4. Mutual confirmation by participants transitions status to 'resolved'.
    """
    _last_analysis_time.clear()

    conv = Conversation(
        is_group=False,
        direct_user_low_id=min(test_user.id, test_user_b.id),
        direct_user_high_id=max(test_user.id, test_user_b.id),
    )
    db_session.add(conv)
    await db_session.commit()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member"),
    ])
    await db_session.commit()

    # 1. Ambiguous message
    msg1 = Message(
        conversation_id=conv.id,
        sender_id=test_user.id,
        content="Let's push the new update sometime tomorrow.",
        message_type="text",
    )
    db_session.add(msg1)
    await db_session.commit()

    mock_finding = AlignmentAnalysisResult(
        mismatch_detected=True,
        category="deadlines",
        severity="medium",
        title="Unclear Launch Timing",
        explanation="The phrase 'sometime tomorrow' lacks a specific time, release window, or timezone.",
        confidence=0.92,
        supporting_message_ids=[str(msg1.id)],
        clarification_question="What exact time and timezone are we scheduling the update for?",
        suggested_reply="Could we target 4 PM EST tomorrow for the update?",
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "detect_alignment", return_value=mock_finding):
        alignment_service = AlignmentService(db_session)
        finding = await alignment_service.analyze_conversation(conv.id, triggering_message_id=msg1.id)

        assert finding is not None
        assert finding.status == "detected"
        assert finding.severity == "medium"
        assert finding.title == "Unclear Launch Timing"
        assert finding.suggested_reply == "Could we target 4 PM EST tomorrow for the update?"
        finding_id = finding.id

    # 2. Bob replies with casual acknowledgment "ok sounds good"
    msg2 = Message(
        conversation_id=conv.id,
        sender_id=test_user_b.id,
        content="ok sounds good",
        message_type="text",
    )
    db_session.add(msg2)
    await db_session.commit()

    # Resolution evaluator determines NO concrete evidence was provided (casual acknowledgment only)
    mock_casual_eval = ResolutionEvaluationResult(
        has_resolution_evidence=False,
        is_resolved=False,
        status_update="clarifying",
        evidence_summary=None,
        confidence=0.89,
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "evaluate_resolution", return_value=mock_casual_eval):
        eval_update = await alignment_service.evaluate_active_findings(conv.id)
        assert eval_update is not None
        assert eval_update.status == "clarifying"
        assert eval_update.resolution_evidence is None

    # 3. Alice provides concrete substantive evidence: "Specifically 4 PM EST with build v1.2"
    msg3 = Message(
        conversation_id=conv.id,
        sender_id=test_user.id,
        content="Let's lock in 4 PM EST tomorrow with build v1.2.",
        message_type="text",
    )
    db_session.add(msg3)
    await db_session.commit()

    mock_concrete_eval = ResolutionEvaluationResult(
        has_resolution_evidence=True,
        is_resolved=True,
        status_update="awaiting_confirmation",
        evidence_summary="Alice clarified exact release window as 4 PM EST with build v1.2.",
        confidence=0.96,
    )

    with patch.object(Settings, "is_provider_configured", return_value=True), \
         patch.object(nvidia_provider, "_ensure_configured", return_value=None), \
         patch.object(nvidia_provider, "evaluate_resolution", return_value=mock_concrete_eval):
        eval_update2 = await alignment_service.evaluate_active_findings(conv.id)
        assert eval_update2 is not None
        assert eval_update2.status == "awaiting_confirmation"
        assert "4 PM EST with build v1.2" in (eval_update2.resolution_evidence or "")

    # 4. Bob confirms the resolution
    confirmed_finding = await alignment_service.confirm_alignment_finding(
        conversation_id=conv.id,
        finding_id=finding_id,
        current_user_id=test_user_b.id,
        comment="Confirmed, ready for 4 PM EST",
    )
    assert confirmed_finding.status == "resolved"
    assert len(confirmed_finding.confirmations) >= 1
    assert confirmed_finding.confirmations[0]["username"] == test_user_b.username


@pytest.mark.asyncio
async def test_alignment_endpoints_confirm_resolve_and_dismiss(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    """Test REST API endpoints for confirm, resolve, and dismiss."""
    conv = Conversation(
        is_group=False,
        direct_user_low_id=min(test_user.id, test_user_b.id),
        direct_user_high_id=max(test_user.id, test_user_b.id),
    )
    db_session.add(conv)
    await db_session.commit()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member"),
    ])
    await db_session.commit()

    finding = AlignmentFinding(
        conversation_id=conv.id,
        mismatch_detected=True,
        category="scope",
        title="Scope Confusion",
        status="detected",
        explanation="Ambiguity over what is included in release.",
        confidence=0.85,
        supporting_message_ids=[],
    )
    db_session.add(finding)
    await db_session.commit()

    # 1. Test manual resolve endpoint
    resp_resolve = await client.post(
        f"/api/v1/conversations/{conv.id}/alignment/{finding.id}/resolve",
        json={"evidence": "Agreed in standup meeting"},
        headers=auth_headers,
    )
    assert resp_resolve.status_code == 200
    data_resolve = resp_resolve.json()
    assert data_resolve["status"] == "resolved"
    assert data_resolve["resolution_evidence"] == "Agreed in standup meeting"

    # 2. Test dismiss endpoint
    finding2 = AlignmentFinding(
        conversation_id=conv.id,
        mismatch_detected=True,
        category="deadlines",
        title="Old Finding",
        status="detected",
        explanation="Old issue.",
        confidence=0.80,
        supporting_message_ids=[],
    )
    db_session.add(finding2)
    await db_session.commit()

    resp_dismiss = await client.post(
        f"/api/v1/conversations/{conv.id}/alignment/{finding2.id}/dismiss",
        json={"reason": "Not relevant"},
        headers=auth_headers,
    )
    assert resp_dismiss.status_code == 200
    assert resp_dismiss.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_recommendation_dismissal_flow(
    client: AsyncClient, test_user: User, test_user_b: User, auth_headers: dict[str, str], db_session: AsyncSession
):
    """Test recommendation dismissal endpoint and filtering."""
    conv = Conversation(
        is_group=False,
        direct_user_low_id=min(test_user.id, test_user_b.id),
        direct_user_high_id=max(test_user.id, test_user_b.id),
    )
    db_session.add(conv)
    await db_session.commit()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id, role="member"),
    ])
    await db_session.commit()

    rec = RecommendationItem(
        conversation_id=conv.id,
        source="youtube",
        title="India vs Australia Final Highlights",
        url="https://www.youtube.com/watch?v=mock123",
        category="cricket",
        extra_data={},
    )
    db_session.add(rec)
    await db_session.commit()

    # Dismiss recommendation via API
    resp_dismiss = await client.post(
        f"/api/v1/conversations/{conv.id}/recommendations/{rec.id}/dismiss",
        headers=auth_headers,
    )
    assert resp_dismiss.status_code == 200
    assert resp_dismiss.json()["is_dismissed"] is True

    # Check ai-items endpoint: dismissed recommendation is filtered out
    resp_items = await client.get(
        f"/api/v1/conversations/{conv.id}/ai-items",
        headers=auth_headers,
    )
    assert resp_items.status_code == 200
    recommendations = resp_items.json()["recommendations"]
    assert not any(r["id"] == str(rec.id) for r in recommendations)
