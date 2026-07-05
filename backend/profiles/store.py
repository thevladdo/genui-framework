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
import logging
from typing import Any, Dict, Optional

from .merge import apply_profile_updates, merge_client_profile

logger = logging.getLogger(__name__)


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

        self._redis_url = redis_url
        self._redis = None
        self._redis_unavailable = False

        self._memory: Dict[str, Dict[str, Any]] = {}

    async def _get_redis(self):
        if not self._redis_url or self._redis_unavailable:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url, encoding="utf-8", decode_responses=True
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning("Profile store: Redis unavailable (%s), using memory", e)
                self._redis = None
                self._redis_unavailable = True
        return self._redis

    def _key(self, tenant: str, user_id: str) -> str:
        return f"{self.key_prefix}{tenant}:{user_id}"


    # CRUD operations
    async def get(self, tenant: str, user_id: str) -> Optional[Dict[str, Any]]:
        key = self._key(tenant, user_id)

        redis = await self._get_redis()
        if redis is not None:
            try:
                raw = await redis.get(key)
                return json.loads(raw) if raw else None
            except Exception as e:
                logger.warning("Profile store: Redis GET failed (%s)", e)

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
                logger.warning("Profile store: Redis SET failed (%s), using memory", e)

        self._memory[key] = profile

    async def delete(self, tenant: str, user_id: str) -> bool:
        """Erase a profile (GDPR right-to-erasure). True if it existed."""
        key = self._key(tenant, user_id)
        existed = False

        redis = await self._get_redis()
        if redis is not None:
            try:
                existed = bool(await redis.delete(key))
            except Exception as e:
                logger.warning("Profile store: Redis DELETE failed (%s)", e)

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
