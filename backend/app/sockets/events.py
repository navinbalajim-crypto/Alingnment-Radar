"""Socket.IO real-time event handlers for connection, chat, and room routing."""

import uuid
from typing import Any, Dict, Optional
from pydantic import ValidationError
import socketio.exceptions
from app.core.logging import logger
from app.core.errors import AppException
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.events import (
    ClientJoinPayload,
    ClientSendMessagePayload,
    ServerMessageAckPayload,
    ServerMessageErrorPayload,
    ServerMessageNewPayload,
)
from app.schemas.message import MessageCreate
from app.services.conversation_service import ConversationService
from app.services.analysis_queue import AnalysisQueue
from app.sockets.connection_manager import connection_manager
from app.sockets.presence import broadcast_presence_change, join_conversation_rooms, send_presence_snapshot
from app.sockets.server import sio
from app.tasks.ai_pipeline import schedule_ai_pipeline


@sio.event
async def connect(sid: str, environ: Dict[str, Any], auth: Optional[Dict[str, Any]] = None):
    """
    Authenticate connecting Socket.IO client via handshake auth token.
    Validates token and binds user session to socket sid.
    """
    logger.info(f"Incoming socket connection request sid={sid}")
    token = None

    if auth and isinstance(auth, dict):
        token = auth.get("token")

    if not token and "HTTP_AUTHORIZATION" in environ:
        auth_header = environ["HTTP_AUTHORIZATION"]
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        logger.warning(f"Connection rejected: missing auth token for sid={sid}")
        raise socketio.exceptions.ConnectionRefusedError("Authentication failed: Missing token")

    if token.startswith("Bearer "):
        token = token[7:]

    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Token missing subject")
        user_id = uuid.UUID(user_id_str)
    except Exception as exc:
        logger.warning(f"Connection rejected: invalid token for sid={sid} - {exc}")
        raise socketio.exceptions.ConnectionRefusedError("Authentication failed: Invalid or expired token")

    # Verify user exists in database
    async with AsyncSessionLocal() as db_session:
        user_repo = UserRepository(db_session)
        user = await user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            logger.warning(f"Connection rejected: user {user_id} inactive or not found")
            raise socketio.exceptions.ConnectionRefusedError("Authentication failed: User account not found")

        # Save session in Socket.IO
        await sio.save_session(sid, {"user_id": str(user.id), "username": user.username})
        connection_manager.register_connection(sid, user.id)
        logger.info(f"Socket authenticated sid={sid}")

        # Presence: auto-join every conversation room this user belongs to (so DM peers and
        # group members who aren't currently viewing this chat still receive presence
        # updates), send this new tab its initial snapshot, and -- only if this is the
        # user's first active connection -- tell the rest of their conversations they're online.
        is_first_connection = len(connection_manager.get_user_sids(user.id)) == 1
        conv_repo = ConversationRepository(db_session)
        conversations = await conv_repo.get_user_conversations(user.id)
        await join_conversation_rooms(sio, sid, conversations)
        await send_presence_snapshot(sio, sid, user.id, conversations)
        if is_first_connection:
            await broadcast_presence_change(sio, user.id, True, conversations)

        return True


@sio.event
async def disconnect(sid: str):
    """Handle socket disconnection, clean up connection state, and -- only if this was the
    user's last remaining connection -- broadcast that they are now offline."""
    user_id = connection_manager.remove_connection(sid)
    logger.info(f"Socket disconnected sid={sid}")
    if user_id is None or connection_manager.is_online(user_id):
        return  # unauthenticated socket, or other tabs/devices for this user are still connected

    async with AsyncSessionLocal() as db_session:
        conv_repo = ConversationRepository(db_session)
        conversations = await conv_repo.get_user_conversations(user_id)
        await broadcast_presence_change(sio, user_id, False, conversations)


@sio.on("conversation:join")
async def handle_conversation_join(sid: str, data: Any):
    """
    Join a conversation room. Server strictly verifies user membership before allowing subscription.
    """
    session = await sio.get_session(sid)
    if not session or "user_id" not in session:
        await sio.emit("message:error", {"code": "UNAUTHORIZED", "message": "Authentication required"}, room=sid)
        return

    try:
        payload = ClientJoinPayload.model_validate(data)
    except ValidationError as val_err:
        await sio.emit("message:error", {"code": "VALIDATION_ERROR", "message": str(val_err)}, room=sid)
        return

    user_id = uuid.UUID(session["user_id"])
    conversation_id = payload.conversation_id

    async with AsyncSessionLocal() as db_session:
        conv_repo = ConversationRepository(db_session)
        is_member = await conv_repo.is_member(conversation_id, user_id)
        if not is_member:
            logger.warning(f"Unauthorized room join attempt for user={user_id} in conversation={conversation_id}")
            await sio.emit(
                "message:error",
                {"code": "FORBIDDEN", "message": "You are not a member of this conversation."},
                room=sid,
            )
            return

        room_name = f"conversation:{conversation_id}"
        await sio.enter_room(sid, room_name)
        logger.info(f"User joined room {room_name}")


@sio.on("message:send")
async def handle_message_send(sid: str, data: Any):
    """
    Receive, validate, persist, broadcast, and schedule AI analysis for chat messages.
    """
    session = await sio.get_session(sid)
    if not session or "user_id" not in session:
        await sio.emit("message:error", {"code": "UNAUTHORIZED", "message": "Authentication required"}, room=sid)
        return

    try:
        payload = ClientSendMessagePayload.model_validate(data)
    except ValidationError as val_err:
        client_id = data.get("client_id") if isinstance(data, dict) else None
        await sio.emit(
            "message:error",
            {"code": "VALIDATION_ERROR", "message": str(val_err), "client_id": client_id},
            room=sid,
        )
        return

    user_id = uuid.UUID(session["user_id"])
    conversation_id = payload.conversation_id

    async with AsyncSessionLocal() as db_session:
        conv_service = ConversationService(db_session)
        try:
            msg_create = MessageCreate(
                content=payload.content,
                message_type=payload.message_type,
                msg_metadata=payload.msg_metadata,
                client_id=payload.client_id,
                reply_to_message_id=payload.reply_to_message_id,
            )
            saved_message = await conv_service.save_message(
                conversation_id=conversation_id,
                sender_id=user_id,
                message_in=msg_create,
            )
            if saved_message.message_type == "text":
                # Same transaction as the message: every persisted text message gets a durable job.
                await AnalysisQueue(db_session).enqueue(saved_message.id, saved_message.conversation_id)
            await db_session.commit()
        except Exception as exc:
            logger.error(f"Failed to persist message from sid={sid}: {type(exc).__name__}")
            await sio.emit(
                "message:error",
                {
                    "code": "PERSISTENCE_ERROR",
                    # Only deliberate application errors (e.g. not a member) are shown; internals never reach the client.
                    "message": str(getattr(exc, "detail", None) or exc) if isinstance(exc, AppException) else "Failed to save message.",
                    "client_id": payload.client_id,
                },
                room=sid,
            )
            return

        room_name = f"conversation:{conversation_id}"

        # 1. Acknowledge to sender
        ack = ServerMessageAckPayload(
            status="ok",
            message_id=saved_message.id,
            conversation_id=saved_message.conversation_id,
            client_id=saved_message.client_id,
            created_at=saved_message.created_at,
        )
        await sio.emit("message:ack", ack.model_dump(mode="json"), room=sid)

        # 2. Broadcast new message to room
        new_event = ServerMessageNewPayload(message=saved_message)
        await sio.emit("message:new", new_event.model_dump(mode="json"), room=room_name)

        # 3. Asynchronously trigger background AI processing
        schedule_ai_pipeline(conversation_id=saved_message.conversation_id, message_id=saved_message.id)


@sio.on("alignment:confirm")
async def handle_alignment_confirm(sid: str, data: Any):
    """Handle real-time participant confirmation of an alignment finding."""
    session = await sio.get_session(sid)
    if not session or "user_id" not in session:
        await sio.emit("message:error", {"code": "UNAUTHORIZED", "message": "Authentication required"}, room=sid)
        return

    user_id = uuid.UUID(session["user_id"])
    conv_id_raw = data.get("conversation_id") if isinstance(data, dict) else None
    finding_id_raw = data.get("finding_id") if isinstance(data, dict) else None
    comment = data.get("comment") if isinstance(data, dict) else None

    if not conv_id_raw or not finding_id_raw:
        await sio.emit("message:error", {"code": "INVALID_DATA", "message": "Missing conversation_id or finding_id"}, room=sid)
        return

    try:
        conversation_id = uuid.UUID(str(conv_id_raw))
        finding_id = uuid.UUID(str(finding_id_raw))
    except ValueError:
        await sio.emit("message:error", {"code": "INVALID_UUID", "message": "Invalid UUID format"}, room=sid)
        return

    async with AsyncSessionLocal() as db_session:
        from app.services.alignment_service import AlignmentService
        service = AlignmentService(db_session)
        try:
            finding = await service.confirm_alignment_finding(
                conversation_id=conversation_id,
                finding_id=finding_id,
                current_user_id=user_id,
                comment=comment,
            )
            await db_session.commit()
            room_name = f"conversation:{conversation_id}"
            await sio.emit("ai:alignment_update", {"finding": finding.model_dump(mode="json")}, room=room_name)
        except Exception as exc:
            logger.error(f"Failed to confirm alignment over socket: {exc}")
            await sio.emit("message:error", {"code": "ALIGNMENT_CONFIRM_ERROR", "message": str(exc)}, room=sid)


@sio.on("alignment:dismiss")
async def handle_alignment_dismiss(sid: str, data: Any):
    """Handle real-time dismissal of an alignment finding."""
    session = await sio.get_session(sid)
    if not session or "user_id" not in session:
        await sio.emit("message:error", {"code": "UNAUTHORIZED", "message": "Authentication required"}, room=sid)
        return

    user_id = uuid.UUID(session["user_id"])
    conv_id_raw = data.get("conversation_id") if isinstance(data, dict) else None
    finding_id_raw = data.get("finding_id") if isinstance(data, dict) else None
    reason = data.get("reason") if isinstance(data, dict) else None

    if not conv_id_raw or not finding_id_raw:
        await sio.emit("message:error", {"code": "INVALID_DATA", "message": "Missing conversation_id or finding_id"}, room=sid)
        return

    try:
        conversation_id = uuid.UUID(str(conv_id_raw))
        finding_id = uuid.UUID(str(finding_id_raw))
    except ValueError:
        await sio.emit("message:error", {"code": "INVALID_UUID", "message": "Invalid UUID format"}, room=sid)
        return

    async with AsyncSessionLocal() as db_session:
        from app.services.alignment_service import AlignmentService
        service = AlignmentService(db_session)
        try:
            finding = await service.dismiss_alignment_finding(
                conversation_id=conversation_id,
                finding_id=finding_id,
                current_user_id=user_id,
                reason=reason,
            )
            await db_session.commit()
            room_name = f"conversation:{conversation_id}"
            await sio.emit("ai:alignment_update", {"finding": finding.model_dump(mode="json")}, room=room_name)
        except Exception as exc:
            logger.error(f"Failed to dismiss alignment over socket: {exc}")
            await sio.emit("message:error", {"code": "ALIGNMENT_DISMISS_ERROR", "message": str(exc)}, room=sid)


@sio.on("recommendation:dismiss")
async def handle_recommendation_dismiss(sid: str, data: Any):
    """Handle real-time dismissal of a recommendation item."""
    session = await sio.get_session(sid)
    if not session or "user_id" not in session:
        await sio.emit("message:error", {"code": "UNAUTHORIZED", "message": "Authentication required"}, room=sid)
        return

    user_id = uuid.UUID(session["user_id"])
    conv_id_raw = data.get("conversation_id") if isinstance(data, dict) else None
    rec_id_raw = data.get("recommendation_id") if isinstance(data, dict) else None

    if not conv_id_raw or not rec_id_raw:
        await sio.emit("message:error", {"code": "INVALID_DATA", "message": "Missing conversation_id or recommendation_id"}, room=sid)
        return

    try:
        conversation_id = uuid.UUID(str(conv_id_raw))
        recommendation_id = uuid.UUID(str(rec_id_raw))
    except ValueError:
        await sio.emit("message:error", {"code": "INVALID_UUID", "message": "Invalid UUID format"}, room=sid)
        return

    async with AsyncSessionLocal() as db_session:
        from app.services.recommendation_service import RecommendationService
        service = RecommendationService(db_session)
        try:
            await service.dismiss_recommendation(
                conversation_id=conversation_id,
                recommendation_id=recommendation_id,
                current_user_id=user_id,
            )
            await db_session.commit()
            room_name = f"conversation:{conversation_id}"
            await sio.emit(
                "ai:recommendation_dismiss",
                {"recommendation_id": str(recommendation_id), "conversation_id": str(conversation_id)},
                room=room_name,
            )
        except Exception as exc:
            logger.error(f"Failed to dismiss recommendation over socket: {exc}")
            await sio.emit("message:error", {"code": "RECOMMENDATION_DISMISS_ERROR", "message": str(exc)}, room=sid)

