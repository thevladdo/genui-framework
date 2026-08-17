"""
Tenant-keyed JSON store.

Third instance of one shape (zone registry, content policy, theme): a
single JSON document per tenant, Redis when configured so every worker
sees the same write, in-memory otherwise, always failing open. Keeping
one implementation means the fallback rule and the corrupt-entry rule
are decided once instead of once per feature.
"""

import json
import time
from typing import Any, Dict, Optional

from utils.redis_conn import shared_redis


class TenantJsonStore:
    """One JSON document per tenant. Redis or in-memory, fail-open."""

    def __init__(self, key_prefix: str, redis_url: Optional[str] = None):
        self.key_prefix = key_prefix
        self._conn = shared_redis(redis_url)
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._memory_expiry: Dict[str, float] = {}

    def _key(self, tenant: str) -> str:
        return f"{self.key_prefix}{tenant}"

    async def get(self, tenant: str) -> Optional[Dict[str, Any]]:
        """This tenant's document, or None when absent or unreadable."""
        redis = await self._conn.get()
        if redis is not None:
            try:
                raw = await redis.get(self._key(tenant))
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                if not raw:
                    return None
                try:
                    data = json.loads(raw)
                except ValueError:
                    return None  # corrupt entry = nothing stored; next set() rewrites it
                return data if isinstance(data, dict) else None

        expires_at = self._memory_expiry.get(tenant)
        if expires_at is not None and time.time() >= expires_at:
            self._memory.pop(tenant, None)
            self._memory_expiry.pop(tenant, None)
            return None
        return self._memory.get(tenant)

    async def set(
        self,
        tenant: str,
        data: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Replace this tenant's document.

        `ttl_seconds` is for documents that describe something in flight
        rather than something configured: they have to expire on their own,
        or every one ever written stays.
        """
        redis = await self._conn.get()
        if redis is not None:
            try:
                payload = json.dumps(data, default=str)
                if ttl_seconds:
                    await redis.set(self._key(tenant), payload, ex=ttl_seconds)
                else:
                    await redis.set(self._key(tenant), payload)
                return
            except Exception as e:
                await self._conn.mark_failure(e)

        self._memory[tenant] = data
        # The fallback has to expire what Redis would have expired, or a process without Redis keeps every entry ever written
        if ttl_seconds:
            self._memory_expiry[tenant] = time.time() + ttl_seconds
        else:
            self._memory_expiry.pop(tenant, None)

    async def storage_backend(self) -> str:
        """'redis' or 'memory': a write in memory lives in one worker only."""
        return "redis" if await self._conn.get() is not None else "memory"
