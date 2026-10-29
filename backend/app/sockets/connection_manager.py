"""Socket.IO connection manager tracking active sessions and socket states."""

import uuid
from typing import Any, Dict, Optional, Set
from app.core.logging import logger


class ConnectionManager:
    """Tracks active socket connections, user mappings, and conversation room subscriptions."""

    def __init__(self):
        # sid -> user_id
        self._sid_to_user: Dict[str, uuid.UUID] = {}
        # user_id -> set of sids
        self._user_to_sids: Dict[uuid.UUID, Set[str]] = {}

    def register_connection(self, sid: str, user_id: uuid.UUID) -> None:
        self._sid_to_user[sid] = user_id
        if user_id not in self._user_to_sids:
            self._user_to_sids[user_id] = set()
        self._user_to_sids[user_id].add(sid)
        logger.info(f"Registered socket connection for sid={sid}")

    def remove_connection(self, sid: str) -> Optional[uuid.UUID]:
        user_id = self._sid_to_user.pop(sid, None)
        if user_id and user_id in self._user_to_sids:
            self._user_to_sids[user_id].discard(sid)
            if not self._user_to_sids[user_id]:
                del self._user_to_sids[user_id]
        logger.info(f"Removed socket connection for sid={sid}")
        return user_id

    def get_user_id(self, sid: str) -> Optional[uuid.UUID]:
        return self._sid_to_user.get(sid)

    def get_user_sids(self, user_id: uuid.UUID) -> Set[str]:
        return self._user_to_sids.get(user_id, set())

    get_user_connections = get_user_sids

    def is_online(self, user_id: uuid.UUID) -> bool:
        return bool(self._user_to_sids.get(user_id))

    def online_user_ids(self) -> Set[uuid.UUID]:
        return set(self._user_to_sids.keys())


connection_manager = ConnectionManager()
