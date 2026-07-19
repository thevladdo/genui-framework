"""
Shared Redis connection with reconnect backoff.

Every store with an in-memory fallback (zone cache, profiles, rate
limiter, metrics) gets its client from here instead of keeping its own
permanent `_redis_unavailable` flag. The contract:

- fail-open: when Redis is not usable *right now*, `get()` returns None
  and the caller serves from its in-memory fallback — never a 500;
- fail-briefly, not permanently: a failure arms an exponential backoff
  window (1s doubling up to 30s); after it expires the next call probes
  Redis again and the stores return to the shared backend as soon as it
  answers. In-memory is a shock absorber for blips, not an operating
  mode — with multiple workers it breaks profiles, rate limits, metrics
  and single-flight (see roadmap/fondamenta/04-scalabilita-multi-istanza.md).

One handle (one connection pool, one backoff clock, one reported state)
is shared per URL across all stores in the process: Redis has a single
real state, so it is probed and reported once — /health reads the same
handle the stores use.
"""

import logging
import re
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_MIN_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0
# Cap every socket wait so one blip costs an operation at most ~2s before the memory fallback kicks in.
_SOCKET_TIMEOUT_SECONDS = 2


class ReconnectingRedis:
    """Lazy Redis client with time-based reconnect instead of a sticky flag."""

    def __init__(
        self,
        url: Optional[str],
        min_backoff: float = _MIN_BACKOFF_SECONDS,
        max_backoff: float = _MAX_BACKOFF_SECONDS,
    ):
        self._url = url
        self._min_backoff = min_backoff
        self._max_backoff = max_backoff
        self._backoff = min_backoff
        self._retry_at = 0.0
        self._client = None
        self._connecting = False  # single-flight guard for concurrent connects

    @property
    def status(self) -> str:
        """'disabled' (no URL) | 'connected' | 'reconnecting'. No I/O."""
        if not self._url:
            return "disabled"
        return "connected" if self._client is not None else "reconnecting"

    async def get(self):
        """The live client, or None (not configured / inside a backoff window)."""
        if not self._url:
            return None
        if self._client is not None:
            return self._client
        if self._connecting or time.monotonic() < self._retry_at:
            return None
        self._connecting = True
        try:
            return await self._connect()
        finally:
            self._connecting = False

    async def mark_failure(self, error: Exception) -> None:
        """Report a failed command: drop the client and arm a backoff window."""
        client, self._client = self._client, None
        if client is None:
            return  # a concurrent failure already armed the window
        await self._aclose(client)
        self._enter_backoff(error)

    async def probe(self) -> str:
        """
        Actively test Redis NOW (health endpoint): pings the live client or
        attempts a connect regardless of the backoff window, so /health is
        truthful on an idle process and recovery is not delayed by backoff.
        """
        if not self._url:
            return "disabled"
        client = self._client
        if client is not None:
            try:
                await client.ping()
                return "connected"
            except Exception as e:
                await self.mark_failure(e)
                return "reconnecting"
        if self._connecting:
            return self.status
        self._connecting = True
        try:
            connected = await self._connect() is not None
        finally:
            self._connecting = False
        return "connected" if connected else "reconnecting"

    async def _connect(self):
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
                socket_timeout=_SOCKET_TIMEOUT_SECONDS,
            )
        except Exception as e:  # import error / malformed URL
            self._enter_backoff(e)
            return None
        try:
            await client.ping()
        except Exception as e:
            await self._aclose(client)
            self._enter_backoff(e)
            return None
        self._client = client
        self._backoff = self._min_backoff
        self._retry_at = 0.0
        logger.info("Redis connected (%s)", self._safe_url())
        return client

    def _enter_backoff(self, error: Exception) -> None:
        self._retry_at = time.monotonic() + self._backoff
        logger.warning(
            "Redis unavailable (%s): in-memory fallback for ~%.0fs, then reconnecting (%s)",
            error,
            self._backoff,
            self._safe_url(),
        )
        self._backoff = min(self._backoff * 2, self._max_backoff)

    def _safe_url(self) -> str:
        """URL for logs with any password redacted."""
        return re.sub(r"://[^@/]*@", "://***@", self._url or "")

    @staticmethod
    async def _aclose(client) -> None:
        closer = getattr(client, "aclose", None) or getattr(client, "close", None)
        if closer is None:
            return
        try:
            await closer()
        except Exception:
            pass


_handles: Dict[str, ReconnectingRedis] = {}


def shared_redis(url: Optional[str]) -> ReconnectingRedis:
    """Process-wide handle per URL: one pool, one backoff clock, one status."""
    handle = _handles.get(url or "")
    if handle is None:
        handle = _handles[url or ""] = ReconnectingRedis(url)
    return handle
