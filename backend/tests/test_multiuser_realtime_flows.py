"""Multi-user and real-time integration tests verifying client isolation, deletion sync, and group room eviction."""

import uuid
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.conversation import Conversation, ConversationMember
from app.models.user import User
from app.schemas.group import CreateGroupRequest
from app.schemas.message import MessageCreate
from app.services.conversation_service import ConversationService
from app.services.group_service import GroupService
from app.services.reminder_service import ReminderService
from app.sockets.connection_manager import connection_manager
from app.sockets.server import sio


@pytest.fixture
async def multi_user_world(db_session: AsyncSession):
    """Create 3 distinct test users and a shared group."""
    user1 = User(email="user1@example.com", username="user1", username_normalized="user1", display_name="User One", is_active=True)
    user2 = User(email="user2@example.com", username="user2", username_normalized="user2", display_name="User Two", is_active=True)
    user3 = User(email="user3@example.com", username="user3", username_normalized="user3", display_name="User Three", is_active=True)
    db_session.add_all([user1, user2, user3])
    await db_session.commit()

    # User1 creates a group with User2
    group_service = GroupService(db_session)
    group = await group_service.create_group(
        creator_id=user1.id,
        group_in=CreateGroupRequest(title="Multi-user Project", initial_member_usernames=[user2.username]),
    )
    await db_session.commit()

    # User1 and User2 also have a direct conversation
    conv_service = ConversationService(db_session)
    dm12 = await conv_service.get_or_create_direct_conversation(user1.id, user2.username)
    await db_session.commit()

    # User3 has a private direct conversation with User2
    dm23 = await conv_service.get_or_create_direct_conversation(user3.id, user2.username)
    await db_session.commit()

    token1 = create_access_token(user_id=str(user1.id), username=user1.username)
    token2 = create_access_token(user_id=str(user2.id), username=user2.username)
    token3 = create_access_token(user_id=str(user3.id), username=user3.username)

    return {
        "user1": user1, "user2": user2, "user3": user3,
        "headers1": {"Authorization": f"Bearer {token1}"},
        "headers2": {"Authorization": f"Bearer {token2}"},
        "headers3": {"Authorization": f"Bearer {token3}"},
        "group": group,
        "dm12": dm12,
        "dm23": dm23,
    }


@pytest.mark.asyncio
async def test_direct_and_group_messaging_isolation(client: AsyncClient, multi_user_world, db_session: AsyncSession):
    world = multi_user_world
    dm_id = world["dm12"].id
    group_id = world["group"].id
    conv_service = ConversationService(db_session)

    # 1. User1 sends DM to User2
    msg_dm = await conv_service.save_message(
        conversation_id=dm_id,
        sender_id=world["user1"].id,
        message_in=MessageCreate(content="Direct confidential msg"),
    )
    await db_session.commit()

    # User2 can read it
    res_u2 = await client.get(f"/api/v1/conversations/{dm_id}/messages", headers=world["headers2"])
    assert res_u2.status_code == 200
    assert any(m["content"] == "Direct confidential msg" for m in res_u2.json()["messages"])

    # User3 is NOT in DM12 -> 403 Forbidden
    res_u3 = await client.get(f"/api/v1/conversations/{dm_id}/messages", headers=world["headers3"])
    assert res_u3.status_code == 403

    # 2. User1 sends to group
    msg_grp = await conv_service.save_message(
        conversation_id=group_id,
        sender_id=world["user1"].id,
        message_in=MessageCreate(content="Group update for members"),
    )
    await db_session.commit()

    # User2 (member) can read it
    res_grp_u2 = await client.get(f"/api/v1/conversations/{group_id}/messages", headers=world["headers2"])
    assert res_grp_u2.status_code == 200
    assert any(m["content"] == "Group update for members" for m in res_grp_u2.json()["messages"])

    # User3 (non-member) cannot read group -> 403 Forbidden
    res_grp_u3 = await client.get(f"/api/v1/conversations/{group_id}/messages", headers=world["headers3"])
    assert res_grp_u3.status_code == 403


@pytest.mark.asyncio
async def test_message_deletion_sync_across_clients(client: AsyncClient, multi_user_world, db_session: AsyncSession):
    world = multi_user_world
    dm_id = world["dm12"].id
    conv_service = ConversationService(db_session)

    # User1 sends a message
    msg = await conv_service.save_message(
        conversation_id=dm_id,
        sender_id=world["user1"].id,
        message_in=MessageCreate(content="Message to delete"),
    )
    await db_session.commit()
    msg_id = str(msg.id)

    # Delete for me (User1)
    del_me = await client.delete(
        f"/api/v1/conversations/{dm_id}/messages/{msg_id}",
        params={"delete_type": "me"},
        headers=world["headers1"],
    )
    assert del_me.status_code == 200

    # User1 view: absent
    u1_msgs = (await client.get(f"/api/v1/conversations/{dm_id}/messages", headers=world["headers1"])).json()["messages"]
    assert not any(m["id"] == msg_id for m in u1_msgs)

    # User2 view: still present intact
    u2_msgs = (await client.get(f"/api/v1/conversations/{dm_id}/messages", headers=world["headers2"])).json()["messages"]
    assert any(m["id"] == msg_id and m["content"] == "Message to delete" for m in u2_msgs)

    # User1 unsends for everyone
    del_everyone = await client.delete(
        f"/api/v1/conversations/{dm_id}/messages/{msg_id}",
        params={"delete_type": "everyone"},
        headers=world["headers1"],
    )
    assert del_everyone.status_code == 200

    # Now User2 view also shows placeholder
    u2_msgs_after = (await client.get(f"/api/v1/conversations/{dm_id}/messages", headers=world["headers2"])).json()["messages"]
    target = next(m for m in u2_msgs_after if m["id"] == msg_id)
    assert target["content"] == "This message was deleted."
    assert target["is_deleted_for_everyone"] is True


@pytest.mark.asyncio
async def test_member_removal_and_socket_room_eviction(client: AsyncClient, multi_user_world, db_session: AsyncSession):
    world = multi_user_world
    group_id = world["group"].id
    user2_id = world["user2"].id

    # Register mock socket for User2 in connection manager
    fake_sid = "user2_active_socket_sid"
    connection_manager.register_connection(fake_sid, user2_id)

    with patch.object(sio, "leave_room", new_callable=AsyncMock) as mock_leave, \
         patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:

        # User1 (admin) removes User2 from the group
        res_remove = await client.delete(
            f"/api/v1/groups/{group_id}/members/{user2_id}",
            headers=world["headers1"],
        )
        assert res_remove.status_code == 200

        # Verify Socket.IO evicted User2's socket from room
        mock_leave.assert_called_with(fake_sid, f"conversation:{group_id}")

        # Verify group:member_removed event was emitted to room
        emitted_events = [c.args[0] for c in mock_emit.call_args_list]
        assert "group:member_removed" in emitted_events

    # User2 can no longer access group messages -> 403 Forbidden
    res_history = await client.get(f"/api/v1/conversations/{group_id}/messages", headers=world["headers2"])
    assert res_history.status_code == 403

    # Clean up connection
    connection_manager.remove_connection(fake_sid)


@pytest.mark.asyncio
async def test_attachment_access_isolation_between_conversations(client: AsyncClient, multi_user_world):
    world = multi_user_world
    dm12_id = world["dm12"].id

    # User1 uploads an attachment to DM12
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    upload_res = await client.post(
        f"/api/v1/conversations/{dm12_id}/attachments",
        files={"file": ("report.png", png_bytes, "image/png")},
        headers=world["headers1"],
    )
    assert upload_res.status_code == 201
    att_id = upload_res.json()["attachments"][0]["id"]

    # User2 (recipient in DM12) can download
    res_u2 = await client.get(
        f"/api/v1/conversations/{dm12_id}/attachments/{att_id}",
        headers=world["headers2"],
    )
    assert res_u2.status_code == 200
    assert res_u2.content == png_bytes

    # User3 (unrelated user) cannot download -> 403 Forbidden
    res_u3 = await client.get(
        f"/api/v1/conversations/{dm12_id}/attachments/{att_id}",
        headers=world["headers3"],
    )
    assert res_u3.status_code == 403


@pytest.mark.asyncio
async def test_reminder_visibility_and_isolation(client: AsyncClient, multi_user_world):
    world = multi_user_world
    dm12_id = world["dm12"].id

    # User1 schedules a reminder in DM12
    res_create = await client.post(
        f"/api/v1/conversations/{dm12_id}/reminders",
        json={
            "title": "DM12 Important Meeting",
            "due_at": "2026-10-28T15:00:00+05:30",
            "advance_reminder_minutes": 15,
        },
        headers=world["headers1"],
    )
    assert res_create.status_code == 201

    # User2 (conversation participant) can view reminders
    res_u2 = await client.get(f"/api/v1/conversations/{dm12_id}/reminders", headers=world["headers2"])
    assert res_u2.status_code == 200
    assert len(res_u2.json()) >= 1

    # User3 (non-participant) cannot view reminders -> 403 Forbidden
    res_u3 = await client.get(f"/api/v1/conversations/{dm12_id}/reminders", headers=world["headers3"])
    assert res_u3.status_code == 403
