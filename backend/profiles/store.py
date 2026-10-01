"""
Profile Store
Server-side persistence for user profiles, keyed by (tenant, user_id).

The server copy is the source of truth for personalization; the frontend IndexedDB profile is a cache that can seed or update it.

Redis when configured (shared, persistent), in-memory otherwise.
A profile is personal data, not a cache: with Redis configured it lives only there.
A copy in one worker's memory could not be reached by an erasure served by another worker, and would come back the next time Redis blinked.
So with Redis unreachable every operation raises StoreUnavailable instead of answering "no profile", "saved" or "erased".
"""

import json
from typing import Any, Callable, Dict, Optional

from utils.redis_conn import StoreUnavailable, atomic_update, shared_redis

from .merge import apply_profile_updates, merge_client_profile

# Bound for the in-memory store used without Redis (development): without a cap it grows one dict entry per user.
_MEMORY_MAX_PROFILES = 2000

# Client-side placeholder for "no one in particular". It is a default,
# never an identity, and a profile stored under it would be one record
# shared by every anonymous visitor.
_ANONYMOUS_PLACEHOLDERS = {"anonymous", "anon", "undefined", "null", "none"}


def is_identified(user_id: Optional[str]) -> bool:
    """
    Whether a request carries a usable identity.

    Personal data needs someone to belong to: without a real user_id
    there is no data subject, so there is nothing to store, nothing to
    export and nothing to erase. Blank, whitespace and the client-side
    anonymous placeholders all mean the same thing here, and the answer
    to all of them is the anonymous path.
    """
    return bool(
        user_id
        and user_id.strip()
        and user_id.strip().lower() not in _ANONYMOUS_PLACEHOLDERS
    )


class ProfileStore:
    """Async profile storage with Redis or in-memory backend."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "genui:profile:",
        ttl_seconds: int = 0,
    ):
        """
        Args:
            redis_url: Redis connection URL; None uses in-memory storage.
            ttl_seconds: Profile retention (0 = keep forever). Useful for
                data-minimization policies (e.g. auto-expire after 90 days
                of inactivity; the TTL refreshes on every write).
        """
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

        self._conn = shared_redis(redis_url)

        self._memory: Dict[str, Dict[str, Any]] = {}

    def _in_memory(self) -> bool:
        return self._conn.status == "disabled"

    async def _redis(self):
        """The live Redis client; StoreUnavailable while Redis does not answer."""
        redis = await self._conn.get()
        if redis is None:
            raise StoreUnavailable("profile")
        return redis

    async def _failed(self, error: Exception) -> None:
        await self._conn.mark_failure(error)
        raise StoreUnavailable("profile") from error

    def _key(self, tenant: str, user_id: str) -> str:
        return f"{self.key_prefix}{tenant}:{user_id}"


    # CRUD operations
    async def get(self, tenant: str, user_id: str) -> Optional[Dict[str, Any]]:
        """The stored profile, or None when there is none."""
        key = self._key(tenant, user_id)
        if self._in_memory():
            return self._memory.get(key)
        redis = await self._redis()
        try:
            raw = await redis.get(key)
        except Exception as e:
            await self._failed(e)
        return _parse(raw)

    async def set(self, tenant: str, user_id: str, profile: Dict[str, Any]) -> None:
        """Replace the stored profile."""
        await self._update(tenant, user_id, lambda current: profile)

    async def _update(
        self,
        tenant: str,
        user_id: str,
        change: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Store change(current profile) and return it, atomically: a write by another request between the read and the write makes Redis run `change` again on that write, so neither is lost.
        """
        # The one place per-user state is created, so the one place that
        # can refuse to create it without a person to attach it to.
        if not is_identified(user_id):
            raise ValueError(
                "Refusing to store a profile without an identified user_id "
                f"(got {user_id!r})"
            )
        key = self._key(tenant, user_id)

        if self._in_memory():
            profile = change(self._memory.get(key))
            self._memory.pop(key, None)  # re-insert = most recently written
            self._evict_memory_if_needed()
            self._memory[key] = profile
            return profile

        def decide(values):
            profile = change(_parse(values[0]))
            return {key: (json.dumps(profile, default=str), self.ttl_seconds or None)}, profile

        return await atomic_update(self._conn, [key], decide, "profile")

    def _evict_memory_if_needed(self) -> None:
        """Bound the fallback store; evict the least-recently-written profiles."""
        if len(self._memory) < _MEMORY_MAX_PROFILES:
            return
        for key in list(self._memory)[: max(1, _MEMORY_MAX_PROFILES // 10)]:
            del self._memory[key]

    async def delete(self, tenant: str, user_id: str) -> bool:
        """
        Erase a profile (GDPR right-to-erasure).
        True if it existed.
        Returns only once the store confirmed the delete; StoreUnavailable otherwise, and the profile is still there.
        """
        key = self._key(tenant, user_id)
        if self._in_memory():
            return self._memory.pop(key, None) is not None
        redis = await self._redis()
        try:
            return bool(await redis.delete(key))
        except Exception as e:
            await self._failed(e)


    # Higher-level operations
    async def apply_updates(
        self,
        tenant: str,
        user_id: str,
        updates: list,
    ) -> Dict[str, Any]:
        """Merge agent-produced updates into the stored profile and persist."""
        return await self._update(
            tenant, user_id, lambda current: apply_profile_updates(current or {}, updates)
        )

    async def sync_client_profile(
        self,
        tenant: str,
        user_id: str,
        client_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge a client (IndexedDB) profile into the server copy and persist."""
        return await self._update(
            tenant, user_id, lambda current: merge_client_profile(current, client_profile)
        )


def _parse(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """A stored profile, or None; a corrupt entry is no profile and the next sync rewrites it."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
