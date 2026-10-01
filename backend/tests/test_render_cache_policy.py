"""
A cached render against the policy in force when it is served.

The segment cache serves one render to a whole segment for up to the stale window.
The content policy is edited live by an operator and promised on the next render.
These tests pin down the meeting point:

- a term banned after a render was cached is not served from the cache, on the sync path and on the SSE path, and the cache is rewritten so the check is paid once;
- a generation that was running while the policy changed does not write or serve the newly banned term;
- a cold-miss waiter that runs out of patience answers 503 instead of generating outside the single-flight lock.
"""

import asyncio
import json
import unittest

try:
    import api.deps as deps
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    import utils.content_policy_store as cps
    from agents.zone_agent import ZoneAgent
    from auth.keys import AuthContext
    from config import settings
    from fastapi import HTTPException
    from utils.content_policy_store import ContentPolicyStore
    from utils.rate_limit import RateLimiter
    from utils.zone_cache import ZoneRenderCache
    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False

TERM = "guaranteed returns"

_ENVELOPE = {
    "components": [
        {"type": "text", "data": {"content": "We serve 120 countries."}},
        {"type": "text", "data": {"content": f"Deposit now for {TERM}."}},
    ],
    "pinned_included": [],
    "personalization_applied": False,
    "confidence": 0.8,
    "reasoning": "policy envelope",
    "profile_factors": [],
}


class _FakeLLM:
    """Replays the envelope; `during` runs while the generation is in flight."""

    def __init__(self, envelope, during=None):
        self._text = json.dumps(envelope)
        self.during = during
        self.calls = 0

    async def complete_json(self, system, user, json_schema=None):
        self.calls += 1
        if self.during:
            await self.during()
        return self._text

    async def stream_json(self, system, user):
        self.calls += 1
        yield self._text[:40]
        if self.during:
            await self.during()
        yield self._text[40:]


class _EmptyStore:
    async def search_async(self, query=None, top_k=None, tenant=None, **kwargs):
        return []


def _shown(value) -> str:
    return json.dumps(value, default=str).lower()


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class _RouterCase(unittest.TestCase):
    """Router on in-memory singletons, the real agent on a fake model."""

    @classmethod
    def setUpClass(cls):
        cls.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")

    def setUp(self):
        saved = (
            zone_router._zone_cache,
            zone_router.get_zone_agent,
            deps._llm_budget,
            deps._zone_config_store,
            auth_deps._rate_limiter,
            cps._STORE,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
            settings.llm_budget_per_hour,
            settings.content_policy,
        )

        def restore():
            (
                zone_router._zone_cache,
                zone_router.get_zone_agent,
                deps._llm_budget,
                deps._zone_config_store,
                auth_deps._rate_limiter,
                cps._STORE,
                settings.zone_cache_enabled,
                settings.holdout_percent,
                settings.redis_url,
                settings.llm_budget_per_hour,
                settings.content_policy,
            ) = saved

        self.addCleanup(restore)
        settings.redis_url = None
        zone_router._zone_cache = ZoneRenderCache()
        deps._llm_budget = None
        deps._zone_config_store = None
        auth_deps._rate_limiter = RateLimiter(limit=1000, window_seconds=60)
        cps._STORE = ContentPolicyStore()
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0
        settings.llm_budget_per_hour = 0
        settings.content_policy = ""
        self.use_llm(_FakeLLM(_ENVELOPE))

    def use_llm(self, llm):
        self.llm = llm
        agent = ZoneAgent(model="test", vector_store=_EmptyStore(), llm_client=llm)
        zone_router.get_zone_agent = lambda: agent

    def ban(self):
        return cps._STORE.set("acme", [TERM])

    request_fields = {}

    def request(self):
        return zone_router.ZoneRenderRequest(
            zone_id="offers", base_prompt="We serve 120 countries.", **self.request_fields
        )

    def key(self):
        request = self.request()
        return zone_router._cache_key_for(request, zone_router._segment_for(request), "acme")

    def render(self):
        return asyncio.run(zone_router._handle_render(self.request(), self.CLIENT))

    def stream(self):
        async def collect():
            response = await zone_router.render_zone_stream(self.request(), self.CLIENT, None)
            return "".join([chunk async for chunk in response.body_iterator])

        events = []
        for block in asyncio.run(collect()).strip().split("\n\n"):
            event, data = block.split("\n", 1)
            events.append((event[len("event: "):], json.loads(data[len("data: "):])))
        return events

    def cached_payload(self):
        return asyncio.run(zone_router.get_zone_cache().get(self.key()))


class TestPolicySavedAfterTheCache(_RouterCase):
    def test_sync_hit_does_not_serve_a_term_banned_after_caching(self):
        first = self.render()
        self.assertIn(TERM, _shown(first.components), "precondition: the term was cached")

        asyncio.run(self.ban())
        second = self.render()

        self.assertEqual(second.meta["cache"]["status"], "fresh")
        self.assertNotIn(TERM, _shown(second.components))
        self.assertEqual(len(second.components), 1)
        self.assertIn(TERM, second.meta["sanitization"]["policy_violations"])
        self.assertEqual(second.meta["render_id"], first.meta["render_id"],
                         "the same variant, reduced; not a new generation")
        self.assertEqual(self.llm.calls, 1)

    def test_the_reduced_render_is_written_back_with_its_age(self):
        self.render()
        cached = self.cached_payload()
        asyncio.run(zone_router.get_zone_cache().set(self.key(), cached.payload, age_seconds=120))
        asyncio.run(self.ban())
        self.render()

        after = self.cached_payload()
        self.assertNotIn(TERM, _shown(after.payload["components"]))
        self.assertGreaterEqual(after.age_seconds, 120,
                                "rewriting must not restart the fresh window")

    def test_a_pinned_card_in_a_dropped_component_comes_back(self):
        pinned = {"type": "link", "title": "Security whitepaper",
                  "url": "https://example.com/security"}
        self.use_llm(_FakeLLM({**_ENVELOPE, "components": [
            {"type": "bento", "data": {"columns": 2, "cards": [
                {"title": "Offer", "description": f"Deposit now for {TERM}."},
                {"title": pinned["title"], "link": pinned["url"]},
            ]}},
        ]}))
        self.request_fields = {"pinned_content": [pinned]}
        self.render()
        asyncio.run(self.ban())
        second = self.render()

        self.assertNotIn(TERM, _shown(second.components))
        self.assertIn(pinned["title"], json.dumps([c.model_dump() for c in second.components]))
        self.assertEqual(second.pinned_content_included, [pinned["url"]])

    def test_sse_hit_does_not_stream_a_term_banned_after_caching(self):
        self.stream()
        asyncio.run(self.ban())
        events = self.stream()

        complete = [data for event, data in events if event == "complete"][0]
        self.assertEqual(complete["meta"]["cache"]["status"], "fresh")
        streamed = [data for event, data in events if event == "component"]
        self.assertNotIn(TERM, _shown(streamed + complete["components"]))
        self.assertIn(TERM, complete["meta"]["sanitization"]["policy_violations"])
        self.assertEqual(self.llm.calls, 1)


class TestPolicySavedDuringGeneration(_RouterCase):
    """The generation read the policy before the save and finishes after it."""

    def setUp(self):
        super().setUp()
        self.use_llm(_FakeLLM(_ENVELOPE, during=self.ban))

    def test_sync_cold_miss_neither_serves_nor_caches_the_term(self):
        # The sync agent reads the policy after the model answers, so the save has to land after that read: patch the read to save first.
        import agents.zone_agent as zone_agent_module

        original = zone_agent_module.effective_policy
        self.use_llm(_FakeLLM(_ENVELOPE))

        async def read_then_save(tenant, env_raw):
            policy = await original(tenant, env_raw)
            await self.ban()
            return policy

        zone_agent_module.effective_policy = read_then_save
        self.addCleanup(setattr, zone_agent_module, "effective_policy", original)

        first = self.render()
        self.assertEqual(first.meta["cache"]["status"], "miss")
        self.assertNotIn(TERM, _shown(first.components))
        self.assertNotIn(TERM, _shown(self.cached_payload().payload["components"]))

    def test_sse_cold_miss_neither_completes_with_nor_caches_the_term(self):
        events = self.stream()

        complete = [data for event, data in events if event == "complete"][0]
        self.assertEqual(complete["meta"]["cache"]["status"], "miss")
        self.assertNotIn(TERM, _shown(complete["components"]))
        self.assertNotIn(TERM, _shown(self.cached_payload().payload["components"]))


class TestColdMissPastTheWait(_RouterCase):
    """The single-flight winner is still generating when a waiter gives up."""

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, zone_router, "_COLD_WAIT_SECONDS", zone_router._COLD_WAIT_SECONDS)
        zone_router._COLD_WAIT_SECONDS = 0.3
        self.assertTrue(asyncio.run(zone_router.get_zone_cache().acquire_refresh_lock(self.key())))

    def test_sync_waiter_answers_503_and_generates_nothing(self):
        with self.assertRaises(HTTPException) as raised:
            self.render()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("Retry-After", raised.exception.headers)
        self.assertEqual(self.llm.calls, 0)

    def test_sse_waiter_ends_with_a_503_event_and_generates_nothing(self):
        events = self.stream()

        self.assertEqual([event for event, _ in events], ["error"])
        self.assertEqual(events[0][1]["status"], 503)
        self.assertIn("retry_after", events[0][1])
        self.assertEqual(self.llm.calls, 0)


if __name__ == "__main__":
    unittest.main()
