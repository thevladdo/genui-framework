"""
Zone Render Cache
Stale-while-revalidate cache for zone renders, keyed by (zone config, segment).

Semantics:
- fresh  (age <= fresh_ttl): serve directly, no LLM call.
- stale  (fresh_ttl < age <= stale_ttl): serve immediately, trigger a
  background re-render guarded by a single-flight lock.
- miss: the caller renders live (cold start) and writes the result back,
  so only the first user of a segment pays the LLM latency.

Backends:
- Redis (redis_url configured): shared across processes, survives restarts.
- In-memory fallback: used when redis_url is unset or Redis is unreachable.
  The cache always fails open — a cache outage degrades to live rendering,
  it never breaks rendering.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache entries whose readable key would be unreasonably long are hashed
_MAX_KEY_LENGTH = 200
_MEMORY_MAX_ENTRIES = 2000

STATUS_FRESH = "fresh"
STATUS_STALE = "stale"


@dataclass
class CacheLookup:
    """Result of a cache read."""
    payload: Dict[str, Any]
    age_seconds: float
    status: str  # STATUS_FRESH | STATUS_STALE


def zone_config_hash(config: Dict[str, Any]) -> str:
    """
    Stable hash of the developer-controlled zone configuration
    (prompts, pinned content, constraints, page context).

    Any change to the zone's configuration produces a new hash, so cached
    renders are invalidated automatically when the developer edits prompts.
    """
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_cache_key(zone_id: str, config_hash: str, segment_key: str) -> str:
    """Compose the full cache key for a (zone, config, segment) triple."""
    key = f"{zone_id}:{config_hash}:{segment_key}"
    if len(key) > _MAX_KEY_LENGTH:
        digest = hashlib.sha256(segment_key.encode("utf-8")).hexdigest()[:16]
        key = f"{zone_id}:{config_hash}:seg-{digest}"
    return key


class ZoneRenderCache:
    """
    SWR cache for zone render payloads.

    All methods are async and never raise on backend failures: Redis
    errors are logged and the in-memory fallback takes over.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        fresh_ttl: int = 300,
        stale_ttl: int = 86400,
        lock_ttl: int = 60,
        key_prefix: str = "genui:zone:",
    ):
        self.fresh_ttl = fresh_ttl
        self.stale_ttl = stale_ttl
        self.lock_ttl = lock_ttl
        self.key_prefix = key_prefix

        self._redis_url = redis_url
        self._redis = None
        self._redis_unavailable = False

        # In-memory fallback: key -> (created_at, payload)
        self._memory: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        # In-memory single-flight locks: key -> lock expiry timestamp
        self._memory_locks: Dict[str, float] = {}


    # Backend plumbing 
    async def _get_redis(self):
        """Lazily connect to Redis; mark unavailable on failure (fail-open)."""
        if not self._redis_url or self._redis_unavailable:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                logger.info("Zone cache connected to Redis at %s", self._redis_url)
            except Exception as e:
                logger.warning(
                    "Zone cache: Redis unavailable (%s), using in-memory fallback", e
                )
                self._redis = None
                self._redis_unavailable = True
        return self._redis

    def _full_key(self, key: str) -> str:
        return f"{self.key_prefix}{key}"


    # Read / write
    async def get(self, key: str) -> Optional[CacheLookup]:
        """Look up a cached render. Returns None on miss or expiry."""
        entry = await self._read_entry(key)
        if entry is None:
            return None

        created_at, payload = entry
        age = max(0.0, time.time() - created_at)

        if age > self.stale_ttl:
            return None

        status = STATUS_FRESH if age <= self.fresh_ttl else STATUS_STALE
        return CacheLookup(payload=payload, age_seconds=age, status=status)

    async def set(self, key: str, payload: Dict[str, Any]) -> None:
        """Store a render payload, resetting its age."""
        created_at = time.time()
        envelope = json.dumps({"created_at": created_at, "payload": payload})

        redis = await self._get_redis()
        if redis is not None:
            try:
                await redis.set(self._full_key(key), envelope, ex=self.stale_ttl)
                return
            except Exception as e:
                logger.warning("Zone cache: Redis SET failed (%s), using memory", e)

        self._evict_memory_if_needed()
        self._memory[key] = (created_at, payload)

    async def _read_entry(self, key: str) -> Optional[Tuple[float, Dict[str, Any]]]:
        redis = await self._get_redis()
        if redis is not None:
            try:
                raw = await redis.get(self._full_key(key))
                if raw is None:
                    return None
                envelope = json.loads(raw)
                return float(envelope["created_at"]), envelope["payload"]
            except Exception as e:
                logger.warning("Zone cache: Redis GET failed (%s), using memory", e)

        entry = self._memory.get(key)
        if entry is None:
            return None
        created_at, _ = entry
        if time.time() - created_at > self.stale_ttl:
            self._memory.pop(key, None)
            return None
        return entry

    def _evict_memory_if_needed(self) -> None:
        """Bound the fallback cache; evict the oldest entries."""
        if len(self._memory) < _MEMORY_MAX_ENTRIES:
            return
        oldest = sorted(self._memory.items(), key=lambda kv: kv[1][0])
        for key, _ in oldest[: max(1, _MEMORY_MAX_ENTRIES // 10)]:
            self._memory.pop(key, None)


    # Single-flight refresh locks
    async def acquire_refresh_lock(self, key: str) -> bool:
        """
        Try to become the single refresher for a stale entry.
        Returns False if another worker already holds the lock.
        """
        redis = await self._get_redis()
        if redis is not None:
            try:
                acquired = await redis.set(
                    self._full_key(f"lock:{key}"),
                    "1",
                    nx=True,
                    ex=self.lock_ttl,
                )
                return bool(acquired)
            except Exception as e:
                logger.warning("Zone cache: Redis lock failed (%s), using memory", e)

        now = time.time()
        expiry = self._memory_locks.get(key)
        if expiry is not None and expiry > now:
            return False
        self._memory_locks[key] = now + self.lock_ttl
        return True

    async def release_refresh_lock(self, key: str) -> None:
        """Release a previously acquired refresh lock."""
        redis = await self._get_redis()
        if redis is not None:
            try:
                await redis.delete(self._full_key(f"lock:{key}"))
                return
            except Exception as e:
                logger.warning("Zone cache: Redis unlock failed (%s)", e)

        self._memory_locks.pop(key, None)


    # Introspection
    async def stats(self) -> Dict[str, Any]:
        """Cache statistics for health/debug endpoints."""
        redis = await self._get_redis()
        return {
            "backend": "redis" if redis is not None else "memory",
            "fresh_ttl": self.fresh_ttl,
            "stale_ttl": self.stale_ttl,
            "memory_entries": len(self._memory),
        }
