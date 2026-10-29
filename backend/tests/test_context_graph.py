"""Comprehensive tests for Live Conversation Context Graph service and API."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.user import User
from app.services.context_graph_service import ContextGraphService


@pytest.mark.asyncio
async def test_context_graph_extraction_scenario(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """
    Test extraction scenario from product spec:
    Navin: "We need to submit the research paper tomorrow."
    Alex: "I will finish it tonight."
    Navin: "What about the references?"
    Alex: "Those are already done."
    Navin: "Is everything ready?"
    """
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id),
    ])

    m1 = Message(conversation_id=conv.id, sender_id=test_user.id, content="We need to submit the research paper tomorrow.")
    m2 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="I will finish it tonight.")
    m3 = Message(conversation_id=conv.id, sender_id=test_user.id, content="What about the references?")
    m4 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="Those are already done.")
    m5 = Message(conversation_id=conv.id, sender_id=test_user.id, content="Is everything ready?")
    db_session.add_all([m1, m2, m3, m4, m5])
    await db_session.commit()

    # Run incremental extraction
    c_service = ContextGraphService(db_session)
    nodes, incs = await c_service.process_messages_incremental(conv.id)
    await db_session.commit()

    graph = await c_service.get_conversation_graph(conv.id, user_id=test_user.id)
    assert graph.conversation_id == conv.id
    assert len(graph.active_nodes) >= 2

    # Check that research paper has deadline 'tomorrow' or 'tonight'
    paper_node = next((n for n in graph.active_nodes if "research paper" in n.topic.lower() or "paper" in n.topic.lower()), None)
    assert paper_node is not None
    assert paper_node.status in ["pending", "in_progress"]

    # Check references are marked completed
    ref_node = next((n for n in graph.active_nodes if "reference" in n.topic.lower()), None)
    assert ref_node is not None
    assert ref_node.status == "completed"


@pytest.mark.asyncio
async def test_contradiction_neutral_detection(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """
    Test neutral contradiction detection:
    Earlier: Alex: "I will finish the paper tonight."
    Later: Alex: "I haven't started the paper yet."
    System neutrally prompts for clarification without accusation.
    """
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=test_user.id),
        ConversationMember(conversation_id=conv.id, user_id=test_user_b.id),
    ])

    m1 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="I will finish the paper tonight.")
    m2 = Message(conversation_id=conv.id, sender_id=test_user_b.id, content="I haven't started the paper yet.")
    db_session.add_all([m1, m2])
    await db_session.commit()

    c_service = ContextGraphService(db_session)
    nodes, incs = await c_service.process_messages_incremental(conv.id)
    await db_session.commit()

    graph = await c_service.get_conversation_graph(conv.id, user_id=test_user.id)
    assert len(graph.inconsistencies) >= 1
    inc = graph.inconsistencies[0]
    assert "finish" in inc.clarification_prompt.lower()
    assert inc.earlier_evidence_message_id == m1.id
    assert inc.later_evidence_message_id == m2.id

    # Test dismissing inconsistency via API
    token = create_access_token(user_id=str(test_user.id), username=test_user.username)
    headers = {"Authorization": f"Bearer {token}"}

    res_dismiss = await client.post(
        f"/api/v1/conversations/{conv.id}/context-graph/inconsistencies/{inc.id}/dismiss",
        headers=headers,
    )
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["is_dismissed"] is True

    # After dismissal, it no longer appears in active inconsistencies
    graph_after = await c_service.get_conversation_graph(conv.id, user_id=test_user.id)
    assert len(graph_after.inconsistencies) == 0


@pytest.mark.asyncio
async def test_context_graph_authorization_and_cleanup(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User
):
    """Test conversation scoping and that message deletion cleans evidence from graph."""
    conv = Conversation(is_group=False)
    db_session.add(conv)
    await db_session.flush()

    # Only test_user is member; test_user_b is an outsider
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id))

    msg = Message(conversation_id=conv.id, sender_id=test_user.id, content="We need to finalize designs by tomorrow.")
    db_session.add(msg)
    await db_session.commit()

    c_service = ContextGraphService(db_session)
    await c_service.process_messages_incremental(conv.id)
    await db_session.commit()

    # Outsider test_user_b receives 403 Forbidden
    token_b = create_access_token(user_id=str(test_user_b.id), username=test_user_b.username)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res_auth = await client.get(
        f"/api/v1/conversations/{conv.id}/context-graph",
        headers=headers_b,
    )
    assert res_auth.status_code == 403

    # Authorized member test_user succeeds
    token_a = create_access_token(user_id=str(test_user.id), username=test_user.username)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_ok = await client.get(
        f"/api/v1/conversations/{conv.id}/context-graph",
        headers=headers_a,
    )
    assert res_ok.status_code == 200
    assert len(res_ok.json()["active_nodes"]) >= 1

    # Deleting message removes it from evidence
    await c_service.handle_message_deletion(conv.id, msg.id)
    await db_session.commit()

    graph_cleaned = await c_service.get_conversation_graph(conv.id, user_id=test_user.id)
    for node in graph_cleaned.active_nodes:
        assert str(msg.id) not in node.evidence_message_ids
