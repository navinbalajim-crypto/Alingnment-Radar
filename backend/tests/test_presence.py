"""Tests for real-time presence: online/offline status for direct chats and live
online-member counts for groups, built on the existing Socket.IO connection lifecycle."""

from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.conversation import Conversation, ConversationMember
from app.models.user import User
from app.sockets.connection_manager import connection_manager
from app.sockets.events import connect, disconnect
from app.sockets.server import sio


@pytest.fixture(autouse=True)
def _clean_connection_manager():
    connection_manager._sid_to_user.clear()
    connection_manager._user_to_sids.clear()
    yield
    connection_manager._sid_to_user.clear()
    connection_manager._user_to_sids.clear()


async def make_dm(db_session: AsyncSession, a: User, b: User) -> Conversation:
    conv = Conversation(is_group=False, direct_user_low_id=min(a.id, b.id), direct_user_high_id=max(a.id, b.id))
    db_session.add(conv)
    await db_session.commit()
    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=a.id, role="member"),
        ConversationMember(conversation_id=conv.id, user_id=b.id, role="member"),
    ])
    await db_session.commit()
    return conv


async def make_group(db_session: AsyncSession, members) -> Conversation:
    conv = Conversation(is_group=True, title="Team")
    db_session.add(conv)
    await db_session.commit()
    db_session.add_all([
        ConversationMember(conversation_id=conv.id, user_id=m.id, role="member") for m in members
    ])
    await db_session.commit()
    return conv


async def do_connect(db_session, sid, user):
    token = create_access_token(user_id=str(user.id), username=user.username)
    with patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
         patch.object(sio, "save_session", new_callable=AsyncMock), \
         patch.object(sio, "enter_room", new_callable=AsyncMock), \
         patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await connect(sid, environ={}, auth={"token": token})
    return mock_emit


async def do_disconnect(db_session, sid):
    with patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
         patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await disconnect(sid)
    return mock_emit


def emitted(mock_emit, event_name):
    return [c.kwargs | {"event": c.args[0], "data": c.args[1]} for c in mock_emit.call_args_list if c.args[0] == event_name]


@pytest.mark.asyncio
async def test_user_becomes_online_after_connecting(db_session, test_user, test_user_b):
    conv = await make_dm(db_session, test_user, test_user_b)
    mock_emit = await do_connect(db_session, "sid-a1", test_user)

    updates = emitted(mock_emit, "presence:update")
    assert any(u["data"]["user_id"] == str(test_user.id) and u["data"]["is_online"] is True for u in updates)
    assert any(u["room"] == f"conversation:{conv.id}" for u in updates)
    assert connection_manager.is_online(test_user.id)


@pytest.mark.asyncio
async def test_user_becomes_offline_after_last_connection_disconnects(db_session, test_user, test_user_b):
    await make_dm(db_session, test_user, test_user_b)
    await do_connect(db_session, "sid-a1", test_user)
    mock_emit = await do_disconnect(db_session, "sid-a1")

    updates = emitted(mock_emit, "presence:update")
    assert any(u["data"]["user_id"] == str(test_user.id) and u["data"]["is_online"] is False for u in updates)
    assert not connection_manager.is_online(test_user.id)


@pytest.mark.asyncio
async def test_one_tab_closing_does_not_mark_user_offline_when_another_tab_remains(db_session, test_user, test_user_b):
    await make_dm(db_session, test_user, test_user_b)
    mock_emit1 = await do_connect(db_session, "sid-tab1", test_user)
    mock_emit2 = await do_connect(db_session, "sid-tab2", test_user)

    # Second tab connecting must NOT re-broadcast "online" (already online from tab 1).
    assert emitted(mock_emit1, "presence:update")  # tab 1: went online
    assert not emitted(mock_emit2, "presence:update")  # tab 2: no change, no duplicate broadcast

    mock_emit3 = await do_disconnect(db_session, "sid-tab1")
    assert not emitted(mock_emit3, "presence:update")  # still online via tab 2
    assert connection_manager.is_online(test_user.id)

    mock_emit4 = await do_disconnect(db_session, "sid-tab2")
    offline_updates = emitted(mock_emit4, "presence:update")
    assert any(u["data"]["is_online"] is False for u in offline_updates)
    assert not connection_manager.is_online(test_user.id)


@pytest.mark.asyncio
async def test_reconnection_restores_presence_correctly(db_session, test_user, test_user_b):
    await make_dm(db_session, test_user, test_user_b)
    await do_connect(db_session, "sid-1", test_user)
    await do_disconnect(db_session, "sid-1")
    assert not connection_manager.is_online(test_user.id)

    mock_emit = await do_connect(db_session, "sid-2", test_user)
    updates = emitted(mock_emit, "presence:update")
    assert any(u["data"]["is_online"] is True for u in updates)
    assert connection_manager.is_online(test_user.id)


@pytest.mark.asyncio
async def test_group_online_count_reflects_distinct_members_not_socket_count(db_session, test_user, test_user_b):
    from app.models.user import User as UserModel
    user_c = UserModel(email="carol@example.com", username="carol", username_normalized="carol", display_name="Carol", is_active=True)
    db_session.add(user_c)
    await db_session.commit()

    group = await make_group(db_session, [test_user, test_user_b, user_c])

    # test_user opens two tabs -- should still only count once.
    mock_a1 = await do_connect(db_session, "sid-a-tab1", test_user)
    group_updates_a1 = emitted(mock_a1, "presence:group_update")
    assert any(u["data"]["conversation_id"] == str(group.id) and u["data"]["online_count"] == 1 for u in group_updates_a1)

    mock_a2 = await do_connect(db_session, "sid-a-tab2", test_user)
    # Second tab for the same user: no transition, so no group broadcast at all.
    assert not emitted(mock_a2, "presence:group_update")

    mock_b = await do_connect(db_session, "sid-b", test_user_b)
    group_updates_b = emitted(mock_b, "presence:group_update")
    assert any(u["data"]["online_count"] == 2 for u in group_updates_b)

    # Closing one of test_user's two tabs doesn't change the distinct count.
    mock_close = await do_disconnect(db_session, "sid-a-tab1")
    assert not emitted(mock_close, "presence:group_update")


@pytest.mark.asyncio
async def test_unauthorized_users_cannot_subscribe_to_unrelated_presence(db_session, test_user, test_user_b):
    """A user with no shared conversation never gets joined to that room, so they can never
    receive presence broadcasts for it."""
    from app.models.user import User as UserModel
    outsider = UserModel(email="eve2@example.com", username="eve2", username_normalized="eve2", display_name="Eve", is_active=True)
    db_session.add(outsider)
    await db_session.commit()

    await make_dm(db_session, test_user, test_user_b)

    with patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
         patch.object(sio, "save_session", new_callable=AsyncMock), \
         patch.object(sio, "enter_room", new_callable=AsyncMock) as mock_enter, \
         patch.object(sio, "emit", new_callable=AsyncMock):
        token = create_access_token(user_id=str(outsider.id), username=outsider.username)
        await connect("sid-outsider", environ={}, auth={"token": token})

    # The outsider is never entered into the DM's room.
    joined_rooms = [c.args[1] for c in mock_enter.call_args_list]
    assert not any("conversation" in r for r in joined_rooms)


@pytest.mark.asyncio
async def test_presence_snapshot_on_connect_reflects_current_state(db_session, test_user, test_user_b):
    conv = await make_dm(db_session, test_user, test_user_b)
    await do_connect(db_session, "sid-b", test_user_b)  # B is online first

    mock_emit = await do_connect(db_session, "sid-a", test_user)
    snapshots = emitted(mock_emit, "presence:snapshot")
    assert len(snapshots) == 1
    assert str(test_user_b.id) in snapshots[0]["data"]["online_user_ids"]
    assert snapshots[0]["room"] == "sid-a"
