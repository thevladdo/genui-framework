"""
Rate Limiter
Fixed-window rate limiting per identity (API key fingerprint).

Redis-backed when configured (shared across processes), in-memory
fallback otherwise. Fails open: a limiter backend outage never blocks
legitimate traffic.
"""

import time
from typing import Dict, Optional, Tuple

from .redis_conn import shared_redis


class RateLimiter:
    """
    Fixed-window limiter: at most `limit` requests per `window_seconds`
    per identity.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int = 60,
        redis_url: Optional[str] = None,
        key_prefix: str = "genui:ratelimit:",
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

        self._conn = shared_redis(redis_url)

        # identity -> (window_start, count)
        self._memory: Dict[str, Tuple[float, int]] = {}

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    async def _get_redis(self):
        """The shared Redis client, or None while unavailable (fail-open)."""
        return await self._conn.get()

    async def allow(self, identity: str, cost: int = 1) -> bool:
        """
        Record `cost` requests for the identity; False when over the limit.

        cost > 1 lets a batch of N renders consume N slots instead of 1,
        so amplified requests are charged for what they actually spend.
        """
        if not self.enabled or cost <= 0:
            return True

        redis = await self._get_redis()
        if redis is not None:
            try:
                window = int(time.time() // self.window_seconds)
                key = f"{self.key_prefix}{identity}:{window}"
                count = await redis.incrby(key, cost)
                if count == cost:  # first writer of this window
                    await redis.expire(key, self.window_seconds)
                return count <= self.limit
            except Exception as e:
                await self._conn.mark_failure(e)

        now = time.time()
        window_start, count = self._memory.get(identity, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        count += cost
        self._memory[identity] = (window_start, count)

        # Opportunistic cleanup of expired windows
        if len(self._memory) > 10000:
            cutoff = now - self.window_seconds
            self._memory = {
                k: v for k, v in self._memory.items() if v[0] >= cutoff
            }

        return count <= self.limit
