"""
Profile Store
Server-side persistence for user profiles, keyed by (tenant, user_id).

The server copy is the source of truth for personalization; the
frontend IndexedDB profile is a cache that can seed or update it.

Backends follow the same pattern as the zone cache: Redis when
configured (shared, persistent), in-memory fallback otherwise, always
failing open.
"""

import json
from typing import Any, Dict, Optional

from utils.redis_conn import shared_redis

from .merge import apply_profile_updates, merge_client_profile

# Bound for the in-memory fallback (aligned with the zone cache cap).
# The fallback is a shock absorber during Redis blips, not a durable
# profile database: without a cap it grows one dict entry per user.
_MEMORY_MAX_PROFILES = 2000


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

    async def _get_redis(self):
        """The shared Redis client, or None while unavailable (fail-open)."""
        return await self._conn.get()

    def _key(self, tenant: str, user_id: str) -> str:
        return f"{self.key_prefix}{tenant}:{user_id}"


    # CRUD operations
    async def get(self, tenant: str, user_id: str) -> Optional[Dict[str, Any]]:
        key = self._key(tenant, user_id)

        redis = await self._get_redis()
        if redis is not None:
            try:
                raw = await redis.get(key)
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                try:
                    return json.loads(raw) if raw else None
                except ValueError:
                    return None  # corrupt entry = no profile; next sync rewrites it

        return self._memory.get(key)

    async def set(self, tenant: str, user_id: str, profile: Dict[str, Any]) -> None:
        key = self._key(tenant, user_id)

        redis = await self._get_redis()
        if redis is not None:
            try:
                await redis.set(
                    key,
                    json.dumps(profile, default=str),
                    ex=self.ttl_seconds or None,
                )
                return
            except Exception as e:
                await self._conn.mark_failure(e)

        self._memory.pop(key, None)  # re-insert = most recently written
        self._evict_memory_if_needed()
        self._memory[key] = profile

    def _evict_memory_if_needed(self) -> None:
        """Bound the fallback store; evict the least-recently-written profiles."""
        if len(self._memory) < _MEMORY_MAX_PROFILES:
            return
        for key in list(self._memory)[: max(1, _MEMORY_MAX_PROFILES // 10)]:
            del self._memory[key]

    async def delete(self, tenant: str, user_id: str) -> bool:
        """Erase a profile (GDPR right-to-erasure). True if it existed."""
        key = self._key(tenant, user_id)
        existed = False

        redis = await self._get_redis()
        if redis is not None:
            try:
                existed = bool(await redis.delete(key))
            except Exception as e:
                await self._conn.mark_failure(e)

        if key in self._memory:
            del self._memory[key]
            existed = True

        return existed


    # Higher-level operations
    async def apply_updates(
        self,
        tenant: str,
        user_id: str,
        updates: list,
    ) -> Dict[str, Any]:
        """Merge agent-produced updates into the stored profile and persist."""
        current = await self.get(tenant, user_id) or {}
        merged = apply_profile_updates(current, updates)
        await self.set(tenant, user_id, merged)
        return merged

    async def sync_client_profile(
        self,
        tenant: str,
        user_id: str,
        client_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge a client (IndexedDB) profile into the server copy and persist."""
        current = await self.get(tenant, user_id)
        merged = merge_client_profile(current, client_profile)
        await self.set(tenant, user_id, merged)
        return merged
