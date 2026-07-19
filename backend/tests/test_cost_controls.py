"""
Tests for the cost controls (roadmap WP-07): a public client key must
not be able to convert traffic into LLM spend without a limit.

The three verified amplifiers, and their guards:
- cache_strategy="live" from the request body -> admin keys only
- unbounded /batch-render counted as ONE rate-limit request -> size cap
  plus proportional charging (cost=N on the shared limiter)
- cold-miss stampede (the single-flight lock only covered the stale
  refresh) -> single-flight on the cold path too, reusing the same lock
Plus the per-tenant LLM generation budget (shared limiter store, so it
is consistent across workers) and an explicit provider timeout.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The router tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import sys
import types
import unittest

from utils.rate_limit import RateLimiter

try:  # app-level deps: available in the backend venv, not in the shell python
    from fastapi import HTTPException

    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from auth.keys import AuthContext
    from config import settings
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


def _fake_payload(render_id="r1"):
    return {
        "render_id": render_id,
        "components": [{"type": "text", "data": {"content": "generated"}}],
        "pinned_content_included": [],
        "personalization_applied": False,
        "meta": {},
        "rendered_at": "2026-07-15T00:00:00+00:00",
    }


class TestRateLimiterCost(unittest.TestCase):
    """allow(cost=N): a batch of N renders consumes N slots, not 1."""

    def test_cost_counts_proportionally(self):
        limiter = RateLimiter(limit=10, window_seconds=60)
        self.assertTrue(asyncio.run(limiter.allow("k", cost=9)))
        self.assertTrue(asyncio.run(limiter.allow("k")))  # 10 <= 10
        self.assertFalse(asyncio.run(limiter.allow("k")))  # 11 > 10

    def test_single_charge_over_limit(self):
        limiter = RateLimiter(limit=5, window_seconds=60)
        self.assertFalse(asyncio.run(limiter.allow("k", cost=6)))

    def test_disabled_and_zero_cost(self):
        self.assertTrue(asyncio.run(RateLimiter(limit=0).allow("k", cost=100)))
        limiter = RateLimiter(limit=1, window_seconds=60)
        self.assertTrue(asyncio.run(limiter.allow("k", cost=0)))
        # the zero-cost call consumed nothing
        self.assertTrue(asyncio.run(limiter.allow("k")))


class _FakeModule:
    """Context manager that swaps a module in sys.modules and restores it."""

    def __init__(self, name, **attrs):
        self.name = name
        self.module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(self.module, key, value)

    def __enter__(self):
        self._old = sys.modules.get(self.name)
        sys.modules[self.name] = self.module
        return self.module

    def __exit__(self, *exc):
        if self._old is not None:
            sys.modules[self.name] = self._old
        else:
            sys.modules.pop(self.name, None)


class TestProviderTimeout(unittest.TestCase):
    """The timeout must reach the SDK client: a hung provider must not
    hold requests open for the SDK's default 10 minutes."""

    def test_openai_chat_client_passes_timeout(self):
        class FakeAsyncOpenAI:
            last = None

            def __init__(self, **kwargs):
                FakeAsyncOpenAI.last = kwargs

        with _FakeModule("openai", AsyncOpenAI=FakeAsyncOpenAI):
            from llm.openai_client import OpenAIChatClient

            OpenAIChatClient(api_key="k", model="m", timeout=42.5)
            self.assertEqual(FakeAsyncOpenAI.last.get("timeout"), 42.5)

            OpenAIChatClient(api_key="k", model="m")  # unset = SDK default
            self.assertNotIn("timeout", FakeAsyncOpenAI.last)

    def test_anthropic_chat_client_passes_timeout(self):
        class FakeAsyncAnthropic:
            last = None

            def __init__(self, **kwargs):
                FakeAsyncAnthropic.last = kwargs

        with _FakeModule("anthropic", AsyncAnthropic=FakeAsyncAnthropic):
            from llm.anthropic_client import AnthropicChatClient

            AnthropicChatClient(api_key="k", model="m", timeout=42.5)
            self.assertEqual(FakeAsyncAnthropic.last.get("timeout"), 42.5)

    def test_embedding_client_passes_timeout(self):
        class FakeOpenAI:
            last = None

            def __init__(self, **kwargs):
                FakeOpenAI.last = kwargs

        with _FakeModule("openai", OpenAI=FakeOpenAI):
            from llm.embeddings import OpenAIEmbeddingClient

            OpenAIEmbeddingClient(model="m", api_key="k", timeout=7.0)
            self.assertEqual(FakeOpenAI.last.get("timeout"), 7.0)


@unittest.skipUnless(HAVE_APP_DEPS, "requires config (backend venv)")
class TestFactoryTimeout(unittest.TestCase):
    def test_create_llm_client_passes_settings_timeout(self):
        class FakeAsyncOpenAI:
            last = None

            def __init__(self, **kwargs):
                FakeAsyncOpenAI.last = kwargs

        old = settings.llm_timeout_seconds
        settings.llm_timeout_seconds = 33.0
        try:
            with _FakeModule("openai", AsyncOpenAI=FakeAsyncOpenAI):
                from llm.factory import create_llm_client

                create_llm_client("gpt-test")
                self.assertEqual(FakeAsyncOpenAI.last.get("timeout"), 33.0)
        finally:
            settings.llm_timeout_seconds = old


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestZoneCostControls(unittest.TestCase):
    """Router-level guarantees, on fresh in-memory singletons."""

    CLIENT = None  # set in setUpClass (AuthContext needs the import)
    ADMIN = None

    @classmethod
    def setUpClass(cls):
        cls.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
        cls.CLIENT2 = AuthContext(tenant="globex", is_admin=False, key_fingerprint="gfp")
        cls.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")

    def setUp(self):
        self._saved = (
            zone_router._zone_cache,
            zone_router._llm_budget,
            auth_deps._rate_limiter,
            settings.llm_budget_per_hour,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
        )
        zone_router._zone_cache = ZoneRenderCache()  # fresh, in-memory
        zone_router._llm_budget = None
        auth_deps._rate_limiter = RateLimiter(limit=1000, window_seconds=60)
        settings.llm_budget_per_hour = 0
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0
        settings.redis_url = None  # the lazy budget singleton must stay in-memory

        self._orig_render = zone_router._render_live
        self.render_calls = []

        async def fake_render(request, tenant, segment=None):
            self.render_calls.append(request.zone_id)
            await asyncio.sleep(0.05)
            return _fake_payload(render_id=f"r{len(self.render_calls)}")

        zone_router._render_live = fake_render

    def tearDown(self):
        zone_router._render_live = self._orig_render
        (
            zone_router._zone_cache,
            zone_router._llm_budget,
            auth_deps._rate_limiter,
            settings.llm_budget_per_hour,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
        ) = self._saved

    def _request(self, zone_id="zone-1", **kwargs):
        return zone_router.ZoneRenderRequest(
            zone_id=zone_id, base_prompt="Show content", **kwargs
        )

    # 1. Single-flight on the cold miss
    def test_concurrent_cold_miss_single_generation(self):
        """Two concurrent requests on the same cold key -> ONE LLM call."""

        async def scenario():
            return await asyncio.gather(
                zone_router._handle_render(self._request(), self.CLIENT),
                zone_router._handle_render(self._request(), self.CLIENT),
            )

        first, second = asyncio.run(scenario())

        self.assertEqual(len(self.render_calls), 1)
        # Both were served the winner's payload
        self.assertEqual(first.meta["render_id"], second.meta["render_id"])
        statuses = {first.meta["cache"]["status"], second.meta["cache"]["status"]}
        self.assertEqual(statuses, {"miss", "coalesced"})

    def test_cold_miss_lock_released_after_generation(self):
        """The next cold miss (different key) must not inherit a stuck lock."""

        async def scenario():
            await zone_router._handle_render(self._request("a"), self.CLIENT)
            cache = zone_router.get_zone_cache()
            key = zone_router._cache_key_for(
                self._request("a"), zone_router._segment_for(self._request("a")), "acme"
            )
            return await cache.acquire_refresh_lock(key)

        self.assertTrue(asyncio.run(scenario()))

    # 2. cache_strategy="live" is admin-only
    def test_client_key_cannot_force_live(self):
        request = self._request(cache_strategy="live")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(zone_router._handle_render(request, self.CLIENT))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(self.render_calls, [])

    def test_admin_key_can_force_live(self):
        request = self._request(cache_strategy="live")
        response = asyncio.run(zone_router._handle_render(request, self.ADMIN))
        self.assertEqual(response.meta["cache"]["status"], "bypass")
        self.assertEqual(len(self.render_calls), 1)

    def test_stream_client_live_rejected_before_streaming(self):
        request = self._request(cache_strategy="live")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(zone_router.render_zone_stream(request, self.CLIENT, None))
        self.assertEqual(ctx.exception.status_code, 403)

    # 3. Batch cap + proportional rate-limit charge
    def test_batch_over_cap_rejected(self):
        requests = [
            self._request(f"z{i}") for i in range(settings.zone_batch_max + 1)
        ]
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(zone_router.batch_render_zones(requests, self.CLIENT))
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertEqual(self.render_calls, [])

    def test_batch_charges_rate_limit_proportionally(self):
        requests = [self._request(f"z{i}") for i in range(3)]
        result = asyncio.run(zone_router.batch_render_zones(requests, self.CLIENT))
        self.assertTrue(all(r["success"] for r in result["results"]))
        # The HTTP request itself was charged by the auth dependency;
        # the endpoint charges the remaining N-1.
        _, count = auth_deps._rate_limiter._memory["cfp"]
        self.assertEqual(count, 2)

    def test_batch_over_rate_limit_rejected(self):
        auth_deps._rate_limiter = RateLimiter(limit=1, window_seconds=60)
        requests = [self._request(f"z{i}") for i in range(3)]
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(zone_router.batch_render_zones(requests, self.CLIENT))
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(self.render_calls, [])

    def test_batch_admin_uncharged(self):
        requests = [self._request(f"z{i}") for i in range(3)]
        asyncio.run(zone_router.batch_render_zones(requests, self.ADMIN))
        self.assertNotIn("afp", auth_deps._rate_limiter._memory)

    # 4. Per-tenant LLM budget
    def test_budget_exhausted_denies_new_generations(self):
        settings.llm_budget_per_hour = 1

        asyncio.run(zone_router._handle_render(self._request("a"), self.CLIENT))
        self.assertEqual(len(self.render_calls), 1)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(zone_router._handle_render(self._request("b"), self.CLIENT))
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(len(self.render_calls), 1)

    def test_budget_exhausted_cache_still_served(self):
        settings.llm_budget_per_hour = 1

        asyncio.run(zone_router._handle_render(self._request("a"), self.CLIENT))
        response = asyncio.run(
            zone_router._handle_render(self._request("a"), self.CLIENT)
        )
        self.assertEqual(response.meta["cache"]["status"], "fresh")
        self.assertEqual(len(self.render_calls), 1)  # hit = zero LLM calls

    def test_budget_is_per_tenant(self):
        settings.llm_budget_per_hour = 1
        asyncio.run(zone_router._handle_render(self._request("a"), self.CLIENT))
        # A different tenant has its own budget window
        asyncio.run(zone_router._handle_render(self._request("a"), self.CLIENT2))
        self.assertEqual(len(self.render_calls), 2)

    def test_budget_admin_exempt(self):
        settings.llm_budget_per_hour = 1
        asyncio.run(zone_router._handle_render(self._request("a"), self.ADMIN))
        asyncio.run(zone_router._handle_render(self._request("b"), self.ADMIN))
        self.assertEqual(len(self.render_calls), 2)

    def test_budget_exhausted_skips_background_refresh(self):
        """Stale entries keep being served from cache instead of refreshing."""
        settings.llm_budget_per_hour = 1

        async def scenario():
            budget = zone_router.get_llm_budget()
            await budget.allow("acme")  # exhaust the single slot
            request = self._request("a")
            segment = zone_router._segment_for(request)
            await zone_router._refresh_in_background(request, "key-a", "acme", segment)

        asyncio.run(scenario())
        self.assertEqual(self.render_calls, [])

    def test_refresh_charges_budget(self):
        settings.llm_budget_per_hour = 1

        async def scenario():
            request = self._request("a")
            segment = zone_router._segment_for(request)
            await zone_router._refresh_in_background(request, "key-a", "acme", segment)

        asyncio.run(scenario())
        self.assertEqual(len(self.render_calls), 1)

    # Stream path: a waiter coalesces on the winner's write, no LLM call
    def test_stream_cold_waiter_coalesces_without_agent(self):
        def _no_agent():
            raise AssertionError("the coalescing waiter must not touch the agent")

        orig_agent = zone_router.get_zone_agent
        zone_router.get_zone_agent = _no_agent
        try:

            async def scenario():
                cache = zone_router.get_zone_cache()
                request = self._request("zs")
                segment = zone_router._segment_for(request)
                key = zone_router._cache_key_for(request, segment, "acme")
                # Simulate an in-flight winner on another worker
                self.assertTrue(await cache.acquire_refresh_lock(key))

                async def winner_writes():
                    await asyncio.sleep(0.3)
                    await cache.set(key, _fake_payload("winner"))
                    await cache.release_refresh_lock(key)

                task = asyncio.create_task(winner_writes())
                response = await zone_router.render_zone_stream(
                    self._request("zs"), self.CLIENT, None
                )
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                await task
                return "".join(chunks)

            stream = asyncio.run(scenario())
        finally:
            zone_router.get_zone_agent = orig_agent

        self.assertIn("event: complete", stream)
        self.assertIn("winner", stream)
        self.assertIn("coalesced", stream)
        self.assertEqual(self.render_calls, [])


if __name__ == "__main__":
    unittest.main()
