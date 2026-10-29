"""Conversation and messaging endpoints under /api/v1/conversations."""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.conversation import ConversationSummary
from app.schemas.message import MessageCreate, MessageDeleteRequest, MessageHistoryResponse, MessageRead
from app.services.conversation_service import ConversationService
from app.sockets.server import sio

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=List[ConversationSummary], status_code=status.HTTP_200_OK)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active conversations for the authenticated user (direct chats and groups)."""
    conv_service = ConversationService(db)
    return await conv_service.list_user_conversations(current_user.id)


@router.post("/direct/{username}", response_model=ConversationSummary, status_code=status.HTTP_200_OK)
async def get_or_create_direct_conversation(
    username: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve existing direct conversation with target user or create one idempotently."""
    conv_service = ConversationService(db)
    return await conv_service.get_or_create_direct_conversation(
        current_user_id=current_user.id,
        target_username=username,
    )


@router.get("/{conversation_id}/messages", response_model=MessageHistoryResponse, status_code=status.HTTP_200_OK)
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    before: Optional[datetime] = Query(None, description="Cursor timestamp for pagination"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Load paginated message history for a conversation after verifying user membership."""
    conv_service = ConversationService(db)
    return await conv_service.get_conversation_messages(
        conversation_id=conversation_id,
        user_id=current_user.id,
        limit=limit,
        before=before,
    )


@router.post("/{conversation_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def send_message_rest(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message via HTTP REST endpoint."""
    conv_service = ConversationService(db)
    saved_message = await conv_service.save_message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        message_in=payload,
    )
    await db.commit()
    # Broadcast to room
    room_name = f"conversation:{conversation_id}"
    await sio.emit("message:new", {"message": saved_message.model_dump(mode="json")}, room=room_name)
    return saved_message


@router.delete("/{conversation_id}/messages/{message_id}", status_code=status.HTTP_200_OK)
async def delete_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    delete_type: str = Query("me", description="'me' for Delete for me, 'everyone' for Unsend for everyone"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message for current user ('me') or unsend for everyone ('everyone')."""
    from app.core.errors import BadRequestError
    if delete_type not in {"me", "everyone"}:
        raise BadRequestError("delete_type must be either 'me' or 'everyone'")

    conv_service = ConversationService(db)
    del_mode, msg_read = await conv_service.delete_message(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=current_user.id,
        delete_type=delete_type,
    )
    await db.commit()

    # Real-time synchronization via Socket.IO
    if del_mode == "everyone":
        room_name = f"conversation:{conversation_id}"
        await sio.emit(
            "message:deleted",
            {
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
                "delete_type": "everyone",
            },
            room=room_name,
        )

    return {"status": "ok", "delete_type": del_mode, "message": msg_read}
