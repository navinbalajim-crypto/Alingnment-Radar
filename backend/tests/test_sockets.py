"""Automated tests for Socket.IO real-time connection, room authorization, and message handling."""

import uuid
from unittest.mock import AsyncMock, patch
import pytest
import socketio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token
from app.models.conversation import Conversation, ConversationMember
from app.models.user import User
from app.schemas.events import ClientJoinPayload, ClientSendMessagePayload
from app.sockets.events import connect, disconnect, handle_conversation_join, handle_message_send
from app.sockets.server import sio


@pytest.mark.asyncio
async def test_socket_connect_authentication_success_and_failure(db_session: AsyncSession, test_user: User):
    sid = "test_sid_123"
    valid_token = create_access_token(user_id=str(test_user.id), username=test_user.username)

    # 1. Connect with valid token
    with patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
         patch.object(sio, "save_session", new_callable=AsyncMock) as mock_save:
        success = await connect(sid, environ={}, auth={"token": valid_token})
        assert success is True
        mock_save.assert_called_once()

    # 2. Connect without token -> raises ConnectionRefusedError
    with pytest.raises(socketio.exceptions.ConnectionRefusedError):
        await connect("bad_sid", environ={}, auth={})

    # 3. Connect with malformed token
    with pytest.raises(socketio.exceptions.ConnectionRefusedError):
        await connect("bad_sid", environ={}, auth={"token": "invalid_jwt"})


@pytest.mark.asyncio
async def test_socket_conversation_join_authorization(db_session: AsyncSession, test_user: User, test_user_b: User):
    sid = "test_sid_join"
    session_data = {"user_id": str(test_user.id), "username": test_user.username}

    # Setup conversation where only test_user is member
    conv = Conversation(is_group=True, title="Secret Room")
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))
    await db_session.commit()

    with patch.object(sio, "get_session", return_value=session_data), \
         patch.object(sio, "enter_room", new_callable=AsyncMock) as mock_enter, \
         patch("app.sockets.events.AsyncSessionLocal", return_value=db_session):

        # Authorized join
        await handle_conversation_join(sid, {"conversation_id": str(conv.id)})
        mock_enter.assert_called_once_with(sid, f"conversation:{conv.id}")


@pytest.mark.asyncio
async def test_socket_message_send_and_broadcast(db_session: AsyncSession, test_user: User):
    sid = "test_sid_send"
    session_data = {"user_id": str(test_user.id), "username": test_user.username}

    conv = Conversation(is_group=True, title="Main Room")
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))
    await db_session.commit()

    with patch.object(sio, "get_session", return_value=session_data), \
         patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit, \
         patch("app.sockets.events.AsyncSessionLocal", return_value=db_session), \
         patch("app.sockets.events.schedule_ai_pipeline") as mock_schedule_ai:

        payload = {
            "conversation_id": str(conv.id),
            "content": "Hello real-time team!",
            "message_type": "text",
            "client_id": "client_uuid_123",
        }

        await handle_message_send(sid, payload)

        # Confirm message:ack and message:new were emitted
        emitted_events = [call.args[0] for call in mock_emit.call_args_list]
        assert "message:ack" in emitted_events
        assert "message:new" in emitted_events

        # Confirm AI pipeline was scheduled asynchronously
        mock_schedule_ai.assert_called_once()
