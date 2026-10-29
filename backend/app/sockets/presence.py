"""Real-time presence: online/offline status for direct chats and live online-member
counts for groups. Presence is purely in-memory (via connection_manager) and never
persisted or derived from anything client-supplied -- only from authenticated socket
connections -- so it cannot be spoofed and needs no extra database writes."""

import uuid
from typing import List
from app.models.conversation import Conversation
from app.sockets.connection_manager import connection_manager


def _group_online_count(conversation: Conversation) -> int:
    """Distinct currently-connected members (a member with 3 open tabs still counts once)."""
    return sum(1 for m in conversation.members if connection_manager.is_online(m.user_id))


async def join_conversation_rooms(sio, sid: str, conversations: List[Conversation]) -> None:
    for conv in conversations:
        await sio.enter_room(sid, f"conversation:{conv.id}")


async def send_presence_snapshot(sio, sid: str, user_id: uuid.UUID, conversations: List[Conversation]) -> None:
    """Initial state for a newly-connected client: who among their DM peers is online now,
    plus the current online-member count for each of their groups."""
    online_user_ids = []
    group_counts = []
    for conv in conversations:
        if conv.is_group:
            group_counts.append({"conversation_id": str(conv.id), "online_count": _group_online_count(conv)})
        else:
            for m in conv.members:
                if m.user_id != user_id and connection_manager.is_online(m.user_id):
                    online_user_ids.append(str(m.user_id))
    await sio.emit(
        "presence:snapshot",
        {"online_user_ids": online_user_ids, "group_online_counts": group_counts},
        room=sid,
    )


async def broadcast_presence_change(sio, user_id: uuid.UUID, is_online: bool, conversations: List[Conversation]) -> None:
    """Called only on an actual online<->offline transition for this user (not on every
    tab open/close), so this never fires on a heartbeat or a reconnect from another tab."""
    for conv in conversations:
        room_name = f"conversation:{conv.id}"
        if conv.is_group:
            await sio.emit(
                "presence:group_update",
                {"conversation_id": str(conv.id), "online_count": _group_online_count(conv)},
                room=room_name,
            )
        else:
            await sio.emit(
                "presence:update",
                {"user_id": str(user_id), "is_online": is_online},
                room=room_name,
            )
