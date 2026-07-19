"""
Tests for Redis reconnect-with-backoff.

The failure these tests pin down: every store used to set a permanent
`_redis_unavailable = True` on the first connection error. With multiple
uvicorn workers, a worker whose FIRST Redis touch happens during a blip
(or a compose start race) silently runs in-memory forever: profiles
diverge per process, rate limits multiply by the worker count, metrics
under-count, single-flight degrades to per-process locks.

The contract after the fix:
- fail-open stays: a Redis outage never raises out of a store;
- the degradation is temporary: after the backoff window the store
  reconnects and returns to Redis as soon as it answers.

No real Redis is needed: `redis.asyncio` is replaced in sys.modules by a
controllable fake whose outages are simulated by flipping `server.up`.
"""

import asyncio
import itertools
import sys
import types
import unittest
from unittest import mock

from metrics.store import MetricsStore
from profiles.store import _MEMORY_MAX_PROFILES, ProfileStore
from utils.rate_limit import RateLimiter
from utils.zone_cache import ZoneRenderCache


def run(coro):
    return asyncio.run(coro)


_url_seq = itertools.count()


def unique_url() -> str:
    """Fresh URL per test: shared_redis() handles are cached per URL."""
    return f"redis://fake-host-{next(_url_seq)}:6379/0"


# Fake redis.asyncio


class FakeRedisServer:
    """In-memory stand-in for a Redis server; flip `up` to simulate outages."""

    def __init__(self):
        self.up = True
        self.data = {}
        self.hashes = {}
        self.connect_attempts = 0

    def has_key(self, fragment: str) -> bool:
        keys = list(self.data) + list(self.hashes)
        return any(fragment in k for k in keys)


class FakeRedisClient:
    def __init__(self, server: FakeRedisServer):
        self._server = server

    def _check(self):
        if not self._server.up:
            raise ConnectionError("simulated redis outage")

    async def ping(self):
        self._check()
        return True

    async def get(self, key):
        self._check()
        return self._server.data.get(key)

    async def set(self, key, value, ex=None, nx=False):
        self._check()
        if nx and key in self._server.data:
            return None
        self._server.data[key] = value
        return True

    async def delete(self, key):
        self._check()
        return 1 if self._server.data.pop(key, None) is not None else 0

    async def incr(self, key):
        self._check()
        value = int(self._server.data.get(key, 0)) + 1
        self._server.data[key] = value
        return value

    async def incrby(self, key, amount):
        self._check()
        value = int(self._server.data.get(key, 0)) + int(amount)
        self._server.data[key] = value
        return value

    async def expire(self, key, ttl):
        self._check()
        return True

    async def hincrby(self, key, field, amount):
        self._check()
        bucket = self._server.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount
        return bucket[field]

    async def hgetall(self, key):
        self._check()
        return dict(self._server.hashes.get(key, {}))

    async def aclose(self):
        return None


def fake_redis_modules(server: FakeRedisServer):
    """sys.modules entries so `import redis.asyncio as aioredis` hits the fake."""

    def from_url(url, **kwargs):
        server.connect_attempts += 1
        # Like redis-py, from_url does no I/O: errors surface on ping().
        return FakeRedisClient(server)

    asyncio_mod = types.ModuleType("redis.asyncio")
    asyncio_mod.from_url = from_url
    redis_mod = types.ModuleType("redis")
    redis_mod.asyncio = asyncio_mod
    return {"redis": redis_mod, "redis.asyncio": asyncio_mod}


class FakeRedisTestCase(unittest.TestCase):
    def setUp(self):
        self.server = FakeRedisServer()
        patcher = mock.patch.dict(sys.modules, fake_redis_modules(self.server))
        patcher.start()
        self.addCleanup(patcher.stop)


# The four stores recover from a blip (root-cause sweep: all of them)


class TestStoresRecoverFromBlip(FakeRedisTestCase):
    """
    Timeline for every store:
      1. Redis down at FIRST touch (the compose-race / sticky-flag case):
         the operation falls back to memory and does not raise.
      2. Redis comes back and the backoff window expires: the next
         operation must land on Redis again — not stay in-memory forever.
    """

    def _timeline(self, store, do_write, fragment_for):
        async def scenario():
            self.server.up = False
            await do_write("first")  # fail-open, no exception
            self.assertFalse(self.server.has_key(fragment_for("first")))

            self.server.up = True
            store._conn._retry_at = 0.0  # deterministic: skip the backoff wait
            await do_write("second")
            self.assertTrue(
                self.server.has_key(fragment_for("second")),
                "store did not return to Redis after the blip (sticky degradation)",
            )

        run(scenario())

    def test_zone_cache_recovers(self):
        cache = ZoneRenderCache(redis_url=unique_url())
        self._timeline(
            cache,
            lambda tag: cache.set(f"k-{tag}", {"v": tag}),
            lambda tag: f"k-{tag}",
        )

    def test_profile_store_recovers(self):
        store = ProfileStore(redis_url=unique_url())
        self._timeline(
            store,
            lambda tag: store.set("tenant", f"user-{tag}", {"name": tag}),
            lambda tag: f"user-{tag}",
        )

    def test_rate_limiter_recovers(self):
        limiter = RateLimiter(limit=100, redis_url=unique_url())
        self._timeline(
            limiter,
            lambda tag: limiter.allow(f"identity-{tag}"),
            lambda tag: f"identity-{tag}",
        )

    def test_metrics_store_recovers(self):
        store = MetricsStore(redis_url=unique_url())
        self._timeline(
            store,
            lambda tag: store.record("tenant", f"zone-{tag}", "personalized", "impression"),
            lambda tag: f"zone-{tag}",
        )


class TestEstablishedConnectionBlip(FakeRedisTestCase):
    """
    A blip AFTER a successful connection: the failing command falls back
    to memory (fail-open), drops the client, and the store reconnects
    once the backoff expires — instead of hammering a dead server.
    """

    def _timeline(self, store, do_write, fragment_for):
        async def scenario():
            await do_write("pre")
            self.assertTrue(self.server.has_key(fragment_for("pre")))
            self.assertEqual(store._conn.status, "connected")

            self.server.up = False
            await do_write("during")  # no exception = fail-open kept
            self.assertFalse(self.server.has_key(fragment_for("during")))
            self.assertEqual(store._conn.status, "reconnecting")

            self.server.up = True
            store._conn._retry_at = 0.0
            await do_write("post")
            self.assertTrue(self.server.has_key(fragment_for("post")))
            self.assertEqual(store._conn.status, "connected")

        run(scenario())

    def test_zone_cache_blip(self):
        cache = ZoneRenderCache(redis_url=unique_url())
        self._timeline(
            cache,
            lambda tag: cache.set(f"k-{tag}", {"v": tag}),
            lambda tag: f"k-{tag}",
        )

    def test_profile_store_blip(self):
        store = ProfileStore(redis_url=unique_url())
        self._timeline(
            store,
            lambda tag: store.set("tenant", f"user-{tag}", {"name": tag}),
            lambda tag: f"user-{tag}",
        )

    def test_rate_limiter_blip(self):
        limiter = RateLimiter(limit=100, redis_url=unique_url())
        self._timeline(
            limiter,
            lambda tag: limiter.allow(f"identity-{tag}"),
            lambda tag: f"identity-{tag}",
        )

    def test_metrics_store_blip(self):
        store = MetricsStore(redis_url=unique_url())
        self._timeline(
            store,
            lambda tag: store.record("tenant", f"zone-{tag}", "personalized", "impression"),
            lambda tag: f"zone-{tag}",
        )


# Backoff mechanics on the shared handle


class TestReconnectBackoff(FakeRedisTestCase):
    def _handle(self, **kwargs):
        from utils.redis_conn import ReconnectingRedis

        return ReconnectingRedis(unique_url(), **kwargs)

    def test_backoff_window_prevents_connect_storm(self):
        handle = self._handle()

        async def scenario():
            self.server.up = False
            self.assertIsNone(await handle.get())
            self.assertIsNone(await handle.get())  # inside the window: no retry
            return self.server.connect_attempts

        self.assertEqual(run(scenario()), 1)

    def test_backoff_grows_capped_and_resets_on_success(self):
        handle = self._handle(min_backoff=1.0, max_backoff=3.0)

        async def scenario():
            self.server.up = False
            await handle.get()
            self.assertEqual(handle._backoff, 2.0)  # 1s window armed, next is 2s
            handle._retry_at = 0.0
            await handle.get()
            self.assertEqual(handle._backoff, 3.0)  # capped at max, not 4s
            handle._retry_at = 0.0
            await handle.get()
            self.assertEqual(handle._backoff, 3.0)

            self.server.up = True
            handle._retry_at = 0.0
            client = await handle.get()
            self.assertIsNotNone(client)
            self.assertEqual(handle._backoff, 1.0)  # success resets the ramp

        run(scenario())

    def test_status_values(self):
        from utils.redis_conn import ReconnectingRedis

        self.assertEqual(ReconnectingRedis(None).status, "disabled")

        handle = self._handle()
        self.assertEqual(handle.status, "reconnecting")  # configured, not connected

        async def scenario():
            await handle.get()
            self.assertEqual(handle.status, "connected")
            await handle.mark_failure(ConnectionError("boom"))
            self.assertEqual(handle.status, "reconnecting")

        run(scenario())

    def test_probe_ignores_backoff_and_sees_recovery(self):
        handle = self._handle()

        async def scenario():
            self.server.up = False
            await handle.get()  # enters a backoff window
            self.server.up = True
            # get() would still say no (window not expired); probe checks NOW
            self.assertIsNone(await handle.get())
            self.assertEqual(await handle.probe(), "connected")
            # ...and the probe result benefits the stores immediately
            self.assertIsNotNone(await handle.get())

        run(scenario())

    def test_probe_detects_dead_established_client(self):
        handle = self._handle()

        async def scenario():
            await handle.get()
            self.assertEqual(handle.status, "connected")
            self.server.up = False
            self.assertEqual(await handle.probe(), "reconnecting")

        run(scenario())


# Profile memory store bound


# /health reflects the real Redis state (venv-only: needs fastapi + full deps)

try:
    import importlib

    importlib.import_module("api.main")
    HAVE_APP = True
except Exception:  # fastapi/qdrant/openai not installed in the shell python
    HAVE_APP = False


@unittest.skipUnless(HAVE_APP, "api.main not importable in this interpreter")
class TestHealthReflectsRedis(FakeRedisTestCase):
    def _get_health(self, redis_url):
        from fastapi.testclient import TestClient

        import api.main as main

        with mock.patch.object(main.settings, "redis_url", redis_url):
            return TestClient(main.app).get("/health").json()

    def test_reports_connected(self):
        body = self._get_health(unique_url())
        self.assertEqual(body["redis"], "connected")

    def test_unreachable_redis_degrades_health(self):
        self.server.up = False
        body = self._get_health(unique_url())
        self.assertEqual(body["redis"], "reconnecting")
        self.assertEqual(body["status"], "degraded")

    def test_disabled_without_dev_open_degrades_health(self):
        import api.main as main

        with mock.patch.object(main.settings, "genui_dev_open", False):
            body = self._get_health(None)
        self.assertEqual(body["redis"], "disabled")
        self.assertEqual(body["status"], "degraded")

    def test_disabled_in_dev_open_is_not_degrading(self):
        import api.main as main

        with mock.patch.object(main.settings, "genui_dev_open", True):
            body = self._get_health(None)
        self.assertEqual(body["redis"], "disabled")
        # Overall status still depends on Qdrant here, so only assert that
        # Redis is not the degrading factor when explicitly in dev-open.
        if body["qdrant_connected"]:
            self.assertEqual(body["status"], "healthy")


class TestProfileMemoryBound(unittest.TestCase):
    def test_memory_store_is_bounded(self):
        store = ProfileStore()  # no redis: pure in-memory fallback

        async def scenario():
            for i in range(_MEMORY_MAX_PROFILES + 500):
                await store.set("tenant", f"user-{i}", {"i": i})

        run(scenario())
        self.assertLessEqual(len(store._memory), _MEMORY_MAX_PROFILES)
        # Oldest evicted, newest kept
        last = _MEMORY_MAX_PROFILES + 499
        self.assertIsNone(run(store.get("tenant", "user-0")))
        self.assertEqual(run(store.get("tenant", f"user-{last}")), {"i": last})

    def test_rewriting_same_profile_does_not_grow(self):
        store = ProfileStore()

        async def scenario():
            for i in range(_MEMORY_MAX_PROFILES * 2):
                await store.set("tenant", "same-user", {"i": i})

        run(scenario())
        self.assertEqual(len(store._memory), 1)


if __name__ == "__main__":
    unittest.main()
