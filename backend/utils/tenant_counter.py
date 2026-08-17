"""
Per-tenant running total.

Fourth store shape alongside the JSON one, and it exists because this is a
counter: two workers indexing at the same time both add, and a read then
write would lose one of them. Redis increments atomically, memory is the
fallback for a single process, and a missing total is None rather than
zero. A caller can tell "nothing counted yet" from "counted, it is zero" 
and rebuild instead of quietly deciding the corpus is empty.
"""

from typing import Dict, Optional

from utils.redis_conn import shared_redis


class TenantCounter:
    """One integer per tenant. Redis or in-memory, fail-open."""

    def __init__(self, key_prefix: str, redis_url: Optional[str] = None):
        self.key_prefix = key_prefix
        self._conn = shared_redis(redis_url)
        self._memory: Dict[str, int] = {}

    def _key(self, tenant: str) -> str:
        return f"{self.key_prefix}{tenant}"

    async def add(self, tenant: str, amount: int) -> Optional[int]:
        """
        Add to this tenant's total; returns the new value.

        A negative amount takes away what left. The total is clamped at
        zero: an estimate that drifted, or a document indexed before the
        counter existed, would otherwise leave it negative and a corpus
        reading as smaller than empty.
        """
        if not amount:
            return await self.get(tenant)
        redis = await self._conn.get()
        if redis is not None:
            try:
                total = int(await redis.incrby(self._key(tenant), amount))
                if total < 0:
                    await redis.set(self._key(tenant), 0)
                    return 0
                return total
            except Exception as e:
                await self._conn.mark_failure(e)
        self._memory[tenant] = max(0, self._memory.get(tenant, 0) + amount)
        return self._memory[tenant]

    async def get(self, tenant: str) -> Optional[int]:
        """This tenant's total, or None when nothing has been counted."""
        redis = await self._conn.get()
        if redis is not None:
            try:
                raw = await redis.get(self._key(tenant))
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                return int(raw) if raw is not None else None
        return self._memory.get(tenant)

    async def set(self, tenant: str, value: int) -> None:
        """Replace the total, used when it is rebuilt from the source of truth."""
        redis = await self._conn.get()
        if redis is not None:
            try:
                await redis.set(self._key(tenant), int(value))
                return
            except Exception as e:
                await self._conn.mark_failure(e)
        self._memory[tenant] = int(value)
