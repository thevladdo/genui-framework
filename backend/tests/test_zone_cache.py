"""
Tests for the zone render cache (in-memory backend, SWR semantics).
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import asyncio
import unittest

from utils.zone_cache import (
    STATUS_FRESH,
    STATUS_STALE,
    ZoneRenderCache,
    build_cache_key,
    zone_config_hash,
)

PAYLOAD = {"components": [{"type": "bento", "data": {"cards": []}}]}


def run(coro):
    return asyncio.run(coro)


class TestZoneConfigHash(unittest.TestCase):
    def test_stable_regardless_of_key_order(self):
        a = zone_config_hash({"zone_id": "z", "base_prompt": "p", "max_items": 6})
        b = zone_config_hash({"max_items": 6, "base_prompt": "p", "zone_id": "z"})
        self.assertEqual(a, b)

    def test_changes_when_prompt_changes(self):
        a = zone_config_hash({"zone_id": "z", "base_prompt": "show articles"})
        b = zone_config_hash({"zone_id": "z", "base_prompt": "show products"})
        self.assertNotEqual(a, b)


class TestBuildCacheKey(unittest.TestCase):
    def test_readable_key(self):
        key = build_cache_key("home", "abc123", "role=developer")
        self.assertEqual(key, "home:abc123:role=developer")

    def test_long_segment_is_hashed(self):
        long_segment = "int=" + "+".join(f"topic-{i}" for i in range(50))
        key = build_cache_key("home", "abc123", long_segment)
        self.assertLessEqual(len(key), 200)
        self.assertIn("seg-", key)


class TestZoneRenderCacheSWR(unittest.TestCase):
    def test_miss_then_fresh_hit(self):
        cache = ZoneRenderCache(fresh_ttl=60, stale_ttl=3600)

        async def scenario():
            self.assertIsNone(await cache.get("k"))
            await cache.set("k", PAYLOAD)
            return await cache.get("k")

        lookup = run(scenario())
        self.assertIsNotNone(lookup)
        self.assertEqual(lookup.status, STATUS_FRESH)
        self.assertEqual(lookup.payload, PAYLOAD)
        self.assertGreaterEqual(lookup.age_seconds, 0)

    def test_stale_after_fresh_ttl(self):
        cache = ZoneRenderCache(fresh_ttl=0, stale_ttl=3600)

        async def scenario():
            await cache.set("k", PAYLOAD)
            await asyncio.sleep(0.01)
            return await cache.get("k")

        lookup = run(scenario())
        self.assertIsNotNone(lookup)
        self.assertEqual(lookup.status, STATUS_STALE)

    def test_expired_after_stale_ttl(self):
        cache = ZoneRenderCache(fresh_ttl=0, stale_ttl=0)

        async def scenario():
            await cache.set("k", PAYLOAD)
            await asyncio.sleep(0.01)
            return await cache.get("k")

        self.assertIsNone(run(scenario()))

    def test_set_resets_age(self):
        cache = ZoneRenderCache(fresh_ttl=60, stale_ttl=3600)

        async def scenario():
            await cache.set("k", {"v": 1})
            await cache.set("k", {"v": 2})
            return await cache.get("k")

        lookup = run(scenario())
        self.assertEqual(lookup.payload, {"v": 2})
        self.assertEqual(lookup.status, STATUS_FRESH)


class TestSingleFlightLock(unittest.TestCase):
    def test_only_one_refresher(self):
        cache = ZoneRenderCache(lock_ttl=60)

        async def scenario():
            first = await cache.acquire_refresh_lock("k")
            second = await cache.acquire_refresh_lock("k")
            return first, second

        first, second = run(scenario())
        self.assertTrue(first)
        self.assertFalse(second)

    def test_lock_released(self):
        cache = ZoneRenderCache(lock_ttl=60)

        async def scenario():
            await cache.acquire_refresh_lock("k")
            await cache.release_refresh_lock("k")
            return await cache.acquire_refresh_lock("k")

        self.assertTrue(run(scenario()))

    def test_lock_expires(self):
        cache = ZoneRenderCache(lock_ttl=0)

        async def scenario():
            await cache.acquire_refresh_lock("k")
            await asyncio.sleep(0.01)
            return await cache.acquire_refresh_lock("k")

        self.assertTrue(run(scenario()))

    def test_locks_are_per_key(self):
        cache = ZoneRenderCache(lock_ttl=60)

        async def scenario():
            a = await cache.acquire_refresh_lock("a")
            b = await cache.acquire_refresh_lock("b")
            return a, b

        a, b = run(scenario())
        self.assertTrue(a)
        self.assertTrue(b)


class TestFailOpen(unittest.TestCase):
    def test_bad_redis_url_falls_back_to_memory(self):
        cache = ZoneRenderCache(
            redis_url="redis://localhost:1",  # nothing listens here
            fresh_ttl=60,
            stale_ttl=3600,
        )

        async def scenario():
            await cache.set("k", PAYLOAD)
            return await cache.get("k")

        lookup = run(scenario())
        self.assertIsNotNone(lookup)
        self.assertEqual(lookup.payload, PAYLOAD)


if __name__ == "__main__":
    unittest.main()
