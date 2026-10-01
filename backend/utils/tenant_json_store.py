"""
Tenant-keyed JSON store.

One shape shared by the zone registry, the content policy and the theme: a single JSON document per tenant, Redis when configured so every worker sees the same write, in-memory otherwise.
Keeping one implementation means the outage rule and the corrupt-entry rule are decided once instead of once per feature.

The outage rule depends on what the document is.
Configuration an operator saved (policy, theme) cannot be regenerated: with Redis configured and unreachable a read serves the last version this process read or wrote, or raises StoreUnavailable, and a write raises, because a write kept in one worker's memory is overwritten by the older Redis copy as soon as Redis answers.
A record of something in flight (authoritative=False) fails open to memory.
"""

import json
import time
from typing import Any, Dict, Optional, Tuple

from utils.redis_conn import StoreUnavailable, shared_redis


class TenantJsonStore:
    """One JSON document per tenant. Redis or in-memory."""

    def __init__(
        self,
        key_prefix: str,
        redis_url: Optional[str] = None,
        authoritative: bool = True,
    ):
        self.key_prefix = key_prefix
        self.authoritative = authoritative
        self._conn = shared_redis(redis_url)
        # Without Redis: the store itself.
        # With Redis and authoritative: the last version read or written (None = known absent).
        # Otherwise: the fallback for writes Redis refused.
        self._memory: Dict[str, Optional[Dict[str, Any]]] = {}
        self._memory_expiry: Dict[str, float] = {}

    def _key(self, tenant: str) -> str:
        return f"{self.key_prefix}{tenant}"

    def _keeps_copies(self) -> bool:
        return self.authoritative and self._conn.status != "disabled"

    async def read(self, tenant: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        (document, last_known). document is None when nothing is stored; last_known is True when Redis did not answer and the document is the last version this process saw.

        Raises StoreUnavailable when Redis did not answer and this process never saw a version (authoritative stores only).
        """
        redis = await self._conn.get()
        if redis is not None:
            try:
                raw = await redis.get(self._key(tenant))
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                document = _parse(raw)
                if self._keeps_copies():
                    self._memory[tenant] = document
                return document, False

        expires_at = self._memory_expiry.get(tenant)
        if expires_at is not None and time.time() >= expires_at:
            self._memory.pop(tenant, None)
            self._memory_expiry.pop(tenant, None)
        if not self._keeps_copies():
            return self._memory.get(tenant), False
        if tenant not in self._memory:
            raise StoreUnavailable("configuration")
        return self._memory[tenant], True

    async def get(self, tenant: str) -> Optional[Dict[str, Any]]:
        """This tenant's document, or None when nothing is stored."""
        document, _ = await self.read(tenant)
        return document

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
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                if self._keeps_copies():
                    self._memory[tenant] = data
                return
        if self._keeps_copies():
            raise StoreUnavailable("configuration")

        self._memory[tenant] = data
        # The fallback has to expire what Redis would have expired, or a process without Redis keeps every entry ever written
        if ttl_seconds:
            self._memory_expiry[tenant] = time.time() + ttl_seconds
        else:
            self._memory_expiry.pop(tenant, None)

    async def storage_backend(self) -> str:
        """'memory' when no Redis is configured: a write then lives in one worker only."""
        return "memory" if self._conn.status == "disabled" else "redis"


def _parse(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """A stored document, or None; a corrupt entry is nothing stored and the next set() rewrites it."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
