"""
Rate Limiter
Fixed-window rate limiting per identity (API key fingerprint).

Redis-backed when configured (shared across processes), in-memory
fallback otherwise. Fails open: a limiter backend outage never blocks
legitimate traffic.
"""

import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


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

        self._redis_url = redis_url
        self._redis = None
        self._redis_unavailable = False

        # identity -> (window_start, count)
        self._memory: Dict[str, Tuple[float, int]] = {}

    @property
    def enabled(self) -> bool:
        return self.limit > 0

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
                logger.warning("Rate limiter: Redis unavailable (%s), using memory", e)
                self._redis = None
                self._redis_unavailable = True
        return self._redis

    async def allow(self, identity: str) -> bool:
        """Record a request for the identity; False when over the limit."""
        if not self.enabled:
            return True

        redis = await self._get_redis()
        if redis is not None:
            try:
                window = int(time.time() // self.window_seconds)
                key = f"{self.key_prefix}{identity}:{window}"
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, self.window_seconds)
                return count <= self.limit
            except Exception as e:
                logger.warning("Rate limiter: Redis failed (%s), using memory", e)

        now = time.time()
        window_start, count = self._memory.get(identity, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        count += 1
        self._memory[identity] = (window_start, count)

        # Opportunistic cleanup of expired windows
        if len(self._memory) > 10000:
            cutoff = now - self.window_seconds
            self._memory = {
                k: v for k, v in self._memory.items() if v[0] >= cutoff
            }

        return count <= self.limit
