"""Tests for WhatsApp-style message deletion (Delete for me & Unsend for everyone)."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.message import MessageCreate
from app.services.conversation_service import ConversationService
from app.services.group_service import GroupService
from app.schemas.group import CreateGroupRequest


@pytest.fixture
async def direct_conversation(db_session: AsyncSession, test_user: User, test_user_b: User) -> Conversation:
    conv_service = ConversationService(db_session)
    summary = await conv_service.get_or_create_direct_conversation(test_user.id, test_user_b.username)
    await db_session.commit()
    conv = await conv_service.conv_repo.get_by_id(summary.id)
    assert conv is not None
    return conv


@pytest.mark.asyncio
async def test_delete_for_me_only_affects_requesting_user(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, auth_headers_b: dict, db_session: AsyncSession, test_user: User
):
    conv_service = ConversationService(db_session)
    msg1 = await conv_service.save_message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        message_in=MessageCreate(content="Message for delete for me test"),
    )
    await db_session.commit()

    # Alice chooses "Delete for me"
    del_res = await client.delete(
        f"/api/v1/conversations/{direct_conversation.id}/messages/{msg1.id}",
        params={"delete_type": "me"},
        headers=auth_headers,
    )
    assert del_res.status_code == 200

    # Alice fetches messages: msg1 is NOT present
    alice_hist = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/messages",
        headers=auth_headers,
    )
    assert alice_hist.status_code == 200
    alice_msg_ids = [m["id"] for m in alice_hist.json()["messages"]]
    assert str(msg1.id) not in alice_msg_ids

    # Bob fetches messages: msg1 IS present and untouched
    bob_hist = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/messages",
        headers=auth_headers_b,
    )
    assert bob_hist.status_code == 200
    bob_msgs = {m["id"]: m for m in bob_hist.json()["messages"]}
    assert str(msg1.id) in bob_msgs
    assert bob_msgs[str(msg1.id)]["content"] == "Message for delete for me test"
    assert bob_msgs[str(msg1.id)]["is_deleted_for_everyone"] is False


@pytest.mark.asyncio
async def test_unsend_for_everyone_author(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, auth_headers_b: dict, db_session: AsyncSession, test_user: User
):
    conv_service = ConversationService(db_session)
    msg1 = await conv_service.save_message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        message_in=MessageCreate(content="Secret draft sent by mistake"),
    )
    await db_session.commit()

    # Alice unsends for everyone
    del_res = await client.delete(
        f"/api/v1/conversations/{direct_conversation.id}/messages/{msg1.id}",
        params={"delete_type": "everyone"},
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert del_res.json()["message"]["is_deleted_for_everyone"] is True

    # Alice view: shows placeholder
    alice_hist = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/messages",
        headers=auth_headers,
    )
    alice_msg = next(m for m in alice_hist.json()["messages"] if m["id"] == str(msg1.id))
    assert alice_msg["content"] == "This message was deleted."
    assert alice_msg["is_deleted_for_everyone"] is True

    # Bob view: also shows placeholder
    bob_hist = await client.get(
        f"/api/v1/conversations/{direct_conversation.id}/messages",
        headers=auth_headers_b,
    )
    bob_msg = next(m for m in bob_hist.json()["messages"] if m["id"] == str(msg1.id))
    assert bob_msg["content"] == "This message was deleted."
    assert bob_msg["is_deleted_for_everyone"] is True


@pytest.mark.asyncio
async def test_non_author_regular_member_cannot_unsend(
    client: AsyncClient, direct_conversation: Conversation, auth_headers: dict, auth_headers_b: dict, db_session: AsyncSession, test_user: User
):
    conv_service = ConversationService(db_session)
    msg1 = await conv_service.save_message(
        conversation_id=direct_conversation.id,
        sender_id=test_user.id,
        message_in=MessageCreate(content="Alice original message"),
    )
    await db_session.commit()

    # Bob attempts to unsend Alice's message for everyone -> 403 Forbidden
    del_res = await client.delete(
        f"/api/v1/conversations/{direct_conversation.id}/messages/{msg1.id}",
        params={"delete_type": "everyone"},
        headers=auth_headers_b,
    )
    assert del_res.status_code == 403


@pytest.mark.asyncio
async def test_group_admin_can_unsend_member_message(
    client: AsyncClient, db_session: AsyncSession, test_user: User, test_user_b: User, auth_headers: dict, auth_headers_b: dict
):
    # Alice creates a group with Bob (Alice is admin, Bob is member)
    group_service = GroupService(db_session)
    group_detail = await group_service.create_group(
        creator_id=test_user.id,
        group_in=CreateGroupRequest(title="Team Alignment", initial_member_usernames=[test_user_b.username]),
    )
    await db_session.commit()

    # Bob posts a message
    conv_service = ConversationService(db_session)
    bob_msg = await conv_service.save_message(
        conversation_id=group_detail.id,
        sender_id=test_user_b.id,
        message_in=MessageCreate(content="Spam message from member"),
    )
    await db_session.commit()

    # Alice (Group Admin) moderates by unsending for everyone
    del_res = await client.delete(
        f"/api/v1/conversations/{group_detail.id}/messages/{bob_msg.id}",
        params={"delete_type": "everyone"},
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert del_res.json()["message"]["is_deleted_for_everyone"] is True
