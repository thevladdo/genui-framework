"""
Tenant-keyed JSON store.

Third instance of one shape (zone registry, content policy, theme): a
single JSON document per tenant, Redis when configured so every worker
sees the same write, in-memory otherwise, always failing open. Keeping
one implementation means the fallback rule and the corrupt-entry rule
are decided once instead of once per feature.
"""

import json
from typing import Any, Dict, Optional

from utils.redis_conn import shared_redis


class TenantJsonStore:
    """One JSON document per tenant. Redis or in-memory, fail-open."""

    def __init__(self, key_prefix: str, redis_url: Optional[str] = None):
        self.key_prefix = key_prefix
        self._conn = shared_redis(redis_url)
        self._memory: Dict[str, Dict[str, Any]] = {}

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
        return self._memory.get(tenant)

    async def set(self, tenant: str, data: Dict[str, Any]) -> None:
        """Replace this tenant's document."""
        redis = await self._conn.get()
        if redis is not None:
            try:
                await redis.set(self._key(tenant), json.dumps(data, default=str))
                return
            except Exception as e:
                await self._conn.mark_failure(e)
        self._memory[tenant] = data

    async def storage_backend(self) -> str:
        """'redis' or 'memory': a write in memory lives in one worker only."""
        return "redis" if await self._conn.get() is not None else "memory"
