"""
Chat sessions, keyed by (tenant, session_id).

The session_id is a random secret minted by the server: never a counter, never an id the client chose.
A session with a user_id is personal data: it lives as long as the profile retention allows, is indexed under its user, and is exported and erased with the profile.
A session without one is pseudonymous and short: only whoever holds its id can reach it, no index points to it, and it expires.
Same outage rule as the profiles: with Redis configured and unreachable every operation raises StoreUnavailable instead of answering "no session" or "saved".
"""

import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from utils.redis_conn import StoreUnavailable, atomic_update, shared_redis

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{16,128}$"

_MEMORY_MAX_SESSIONS = 2000


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


class ChatSessionStore:
    def __init__(
        self,
        redis_url: Optional[str] = None,
        anonymous_ttl_seconds: int = 1800,
        user_ttl_seconds: int = 0,
        key_prefix: str = "genui:chat:",
    ):
        """
        Args:
            anonymous_ttl_seconds: Lifetime of a session without a user, refreshed on every write.
            user_ttl_seconds: Lifetime of a session with a user, refreshed on every write (0 = no expiry, like the profile it follows).
        """
        self.key_prefix = key_prefix
        self.anonymous_ttl_seconds = anonymous_ttl_seconds
        self.user_ttl_seconds = user_ttl_seconds
        self._conn = shared_redis(redis_url)
        # expires_at 0 = no expiry
        self._memory: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def _in_memory(self) -> bool:
        return self._conn.status == "disabled"

    def _key(self, tenant: str, session_id: str) -> str:
        return f"{self.key_prefix}session:{tenant}:{session_id}"

    def _index_key(self, tenant: str, user_id: str) -> str:
        return f"{self.key_prefix}user:{tenant}:{user_id}"

    def ttl_for(self, record: Dict[str, Any]) -> Optional[int]:
        ttl = self.user_ttl_seconds if record.get("user_id") else self.anonymous_ttl_seconds
        return ttl or None

    async def _redis(self):
        redis = await self._conn.get()
        if redis is None:
            raise StoreUnavailable("chat session")
        return redis

    async def _failed(self, error: Exception) -> None:
        await self._conn.mark_failure(error)
        raise StoreUnavailable("chat session") from error

    def _memory_get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._memory.get(key)
        if entry is None:
            return None
        expires_at, record = entry
        if expires_at and expires_at < time.time():
            del self._memory[key]
            return None
        return record

    async def get(self, tenant: str, session_id: str) -> Optional[Dict[str, Any]]:
        key = self._key(tenant, session_id)
        if self._in_memory():
            return self._memory_get(key)
        redis = await self._redis()
        try:
            raw = await redis.get(key)
        except Exception as e:
            await self._failed(e)
        return _parse(raw)

    async def save(self, tenant: str, session_id: str, record: Dict[str, Any]) -> None:
        """A session with a user joins that user's index in the same transaction."""
        key = self._key(tenant, session_id)
        ttl = self.ttl_for(record)
        user_id = record.get("user_id")

        if self._in_memory():
            self._memory.pop(key, None)
            if len(self._memory) >= _MEMORY_MAX_SESSIONS:
                for old in list(self._memory)[: max(1, _MEMORY_MAX_SESSIONS // 10)]:
                    del self._memory[old]
            self._memory[key] = (time.time() + ttl if ttl else 0, record)
            return

        keys = [key] + ([self._index_key(tenant, user_id)] if user_id else [])

        def decide(values):
            writes = {key: (json.dumps(record, default=str), ttl)}
            if user_id:
                ids = _parse_ids(values[1])
                if session_id not in ids:
                    ids.append(session_id)
                # The index lives as long as its newest session, so an erasure always finds every session
                writes[keys[1]] = (json.dumps(ids), ttl)
            return writes, None

        await atomic_update(self._conn, keys, decide, "chat session")

    async def delete(self, tenant: str, session_id: str) -> bool:
        """True if it existed. A stale entry left in the user index is skipped by export and erased by delete_user."""
        key = self._key(tenant, session_id)
        if self._in_memory():
            return self._memory.pop(key, None) is not None
        redis = await self._redis()
        try:
            return bool(await redis.delete(key))
        except Exception as e:
            await self._failed(e)

    async def sessions_of(self, tenant: str, user_id: str) -> List[Tuple[str, Dict[str, Any]]]:
        if self._in_memory():
            prefix = self._key(tenant, "")
            found = []
            for key in list(self._memory):
                record = self._memory_get(key) if key.startswith(prefix) else None
                if record is not None and record.get("user_id") == user_id:
                    found.append((key[len(prefix):], record))
            return found
        redis = await self._redis()
        try:
            ids = _parse_ids(await redis.get(self._index_key(tenant, user_id)))
            records = [(sid, _parse(await redis.get(self._key(tenant, sid)))) for sid in ids]
        except Exception as e:
            await self._failed(e)
        return [(sid, record) for sid, record in records if record is not None]

    async def delete_user(self, tenant: str, user_id: str) -> int:
        """
        Erase every session of one user and the index; returns how many of those sessions still existed.
        The index and the sessions it lists are watched, so a session saved while the erasure runs makes it run again instead of surviving it.
        """
        if self._in_memory():
            gone = await self.sessions_of(tenant, user_id)
            for sid, _ in gone:
                del self._memory[self._key(tenant, sid)]
            return len(gone)

        index_key = self._index_key(tenant, user_id)
        redis = await self._redis()
        try:
            listed = _parse_ids(await redis.get(index_key))
        except Exception as e:
            await self._failed(e)
        session_keys = [self._key(tenant, sid) for sid in listed]

        def decide(values):
            ids = set(listed) | set(_parse_ids(values[0]))
            writes = {self._key(tenant, sid): None for sid in ids}
            writes[index_key] = None
            # An id left in the index after its session expired or was forgotten is not an erasure
            return writes, sum(1 for value in values[1:] if value)

        return await atomic_update(self._conn, [index_key] + session_keys, decide, "chat session")


def _parse(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _parse_ids(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        ids = json.loads(raw)
    except ValueError:
        return []
    return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []
