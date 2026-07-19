"""
Tests for the zone config registry (roadmap S1): config as data.

The invariant: anything that must be approved, versioned, or edited by
non-developers (prompts, pinned content, rendering constraints) must be
DATA the server owns, not code in the host page. When an APPROVED
registry entry exists for (tenant, zone_id), the render path serves
exactly that config; host props remain the fallback so existing
integrations keep working unchanged; tenants never read each other's
entries.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The router tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import unittest

from pydantic import ValidationError

from zones import STATUS_APPROVED, STATUS_DRAFT, ZoneConfigStore

try:  # app-level deps: available in the backend venv, not in the shell python
    import api.deps as deps
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from auth.keys import AuthContext
    from config import settings
    from utils.rate_limit import RateLimiter
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


REGISTRY_CONFIG = {
    "base_prompt": "REGISTRY PROMPT: show the governed pricing content",
    "context_prompt": "Approved context",
    "pinned_content": [
        {"type": "link", "url": "https://example.com/legal", "title": "Governed pinned"}
    ],
    "preferred_component_type": "bento",
    "max_items": 3,
}


class TestZoneConfigStore(unittest.TestCase):
    """Pure store semantics (in-memory backend)."""

    def setUp(self):
        self.store = ZoneConfigStore()

    def _upsert(self, tenant="acme", zone_id="pricing", config=None, **kwargs):
        return asyncio.run(
            self.store.upsert(tenant, zone_id, config or dict(REGISTRY_CONFIG), **kwargs)
        )

    def test_upsert_and_get_roundtrip(self):
        record = self._upsert()
        self.assertEqual(record["version"], 1)
        self.assertEqual(record["status"], STATUS_APPROVED)
        self.assertEqual(
            record["config"]["base_prompt"], REGISTRY_CONFIG["base_prompt"]
        )

        stored = asyncio.run(self.store.get("acme", "pricing"))
        self.assertEqual(stored, record)

    def test_config_defaults_are_materialized(self):
        """A partial config stores the FULL governed block: the record is
        the complete truth of what was approved, defaults included."""
        record = self._upsert(config={"base_prompt": "Only a prompt"})
        self.assertEqual(record["config"]["max_items"], 6)
        self.assertIsNone(record["config"]["preferred_component_type"])
        self.assertEqual(record["config"]["pinned_content"], [])

    def test_version_increments_on_upsert(self):
        self._upsert()
        record = self._upsert(config={"base_prompt": "v2"})
        self.assertEqual(record["version"], 2)

    def test_draft_is_not_approved(self):
        self._upsert(status=STATUS_DRAFT)
        self.assertIsNone(asyncio.run(self.store.get_approved("acme", "pricing")))
        # ...but it exists for preview/CRUD (phase 2)
        record = asyncio.run(self.store.get("acme", "pricing"))
        self.assertEqual(record["status"], STATUS_DRAFT)

    def test_approving_after_draft_serves(self):
        self._upsert(status=STATUS_DRAFT)
        self._upsert(status=STATUS_APPROVED)
        record = asyncio.run(self.store.get_approved("acme", "pricing"))
        self.assertEqual(record["version"], 2)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            self._upsert(status="published")

    def test_unknown_config_key_rejected(self):
        """A typo'd key must fail at write time, not silently un-govern a field."""
        with self.assertRaises(ValidationError):
            self._upsert(config={"base_promt": "typo"})

    def test_tenant_isolation(self):
        self._upsert(tenant="acme")
        self.assertIsNone(asyncio.run(self.store.get("globex", "pricing")))
        self.assertIsNone(asyncio.run(self.store.get_approved("globex", "pricing")))

    def test_delete(self):
        self._upsert()
        self.assertTrue(asyncio.run(self.store.delete("acme", "pricing")))
        self.assertIsNone(asyncio.run(self.store.get("acme", "pricing")))
        self.assertFalse(asyncio.run(self.store.delete("acme", "pricing")))


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestRegistryResolution(unittest.TestCase):
    """Router-level guarantee: the render path resolves config as data."""

    @classmethod
    def setUpClass(cls):
        cls.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
        cls.GLOBEX = AuthContext(tenant="globex", is_admin=False, key_fingerprint="gfp")
        cls.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")

    def setUp(self):
        self._saved = (
            zone_router._zone_cache,
            zone_router._llm_budget,
            deps._zone_config_store,
            auth_deps._rate_limiter,
            settings.llm_budget_per_hour,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
        )
        zone_router._zone_cache = ZoneRenderCache()  # fresh, in-memory
        zone_router._llm_budget = None
        deps._zone_config_store = ZoneConfigStore()
        auth_deps._rate_limiter = RateLimiter(limit=1000, window_seconds=60)
        settings.llm_budget_per_hour = 0
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0
        settings.redis_url = None

        self.store = deps._zone_config_store
        self._orig_render = zone_router._render_live
        self.rendered_requests = []

        async def fake_render(request, tenant, segment=None):
            self.rendered_requests.append(request)
            return {
                "render_id": f"r{len(self.rendered_requests)}",
                "components": [{"type": "text", "data": {"content": "generated"}}],
                "pinned_content_included": [],
                "personalization_applied": False,
                "meta": {},
                "rendered_at": "2026-07-17T00:00:00+00:00",
            }

        zone_router._render_live = fake_render

    def tearDown(self):
        zone_router._render_live = self._orig_render
        (
            zone_router._zone_cache,
            zone_router._llm_budget,
            deps._zone_config_store,
            auth_deps._rate_limiter,
            settings.llm_budget_per_hour,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
        ) = self._saved

    def _request(self, zone_id="pricing", **kwargs):
        kwargs.setdefault("base_prompt", "HOST PROPS prompt")
        kwargs.setdefault("max_items", 6)
        return zone_router.ZoneRenderRequest(zone_id=zone_id, **kwargs)

    def _upsert(self, tenant="acme", zone_id="pricing", **kwargs):
        asyncio.run(
            self.store.upsert(tenant, zone_id, dict(REGISTRY_CONFIG), **kwargs)
        )

    def test_registry_entry_wins_over_props(self):
        self._upsert()
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))

        rendered = self.rendered_requests[0]
        self.assertEqual(rendered.base_prompt, REGISTRY_CONFIG["base_prompt"])
        self.assertEqual(rendered.context_prompt, "Approved context")
        self.assertEqual(rendered.preferred_component_type, "bento")
        self.assertEqual(rendered.max_items, 3)
        self.assertEqual(
            [p.title for p in rendered.pinned_content], ["Governed pinned"]
        )

    def test_without_entry_host_props_apply(self):
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        self.assertEqual(self.rendered_requests[0].base_prompt, "HOST PROPS prompt")

    def test_draft_entry_not_served(self):
        self._upsert(status=STATUS_DRAFT)
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        self.assertEqual(self.rendered_requests[0].base_prompt, "HOST PROPS prompt")

    def test_tenant_does_not_read_another_tenants_entry(self):
        self._upsert(tenant="globex")

        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        self.assertEqual(self.rendered_requests[0].base_prompt, "HOST PROPS prompt")

        asyncio.run(zone_router._handle_render(self._request(), self.GLOBEX))
        self.assertEqual(
            self.rendered_requests[1].base_prompt, REGISTRY_CONFIG["base_prompt"]
        )

    def test_registry_edit_invalidates_cached_renders(self):
        """The resolved config feeds the cache key: a new approved version
        must produce a cold miss, not keep serving the old cached render."""
        self._upsert()
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        self.assertEqual(len(self.rendered_requests), 1)  # second was a cache hit

        config = dict(REGISTRY_CONFIG, base_prompt="EDITED PROMPT v2")
        asyncio.run(self.store.upsert("acme", "pricing", config))
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        self.assertEqual(len(self.rendered_requests), 2)
        self.assertEqual(self.rendered_requests[1].base_prompt, "EDITED PROMPT v2")

    def test_stream_path_resolves_registry(self):
        """A cached render (registry-resolved key) must be a stream HIT for a
        request with different host props: the stream path resolves too."""
        self._upsert()
        asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))

        def _no_agent():
            raise AssertionError("cache hit expected: the agent must not run")

        orig_agent = zone_router.get_zone_agent
        zone_router.get_zone_agent = _no_agent
        try:
            async def consume():
                response = await zone_router.render_zone_stream(
                    self._request(base_prompt="totally different props"),
                    self.CLIENT,
                    None,
                )
                return [chunk async for chunk in response.body_iterator]

            events = "".join(asyncio.run(consume()))
        finally:
            zone_router.get_zone_agent = orig_agent

        self.assertIn("event: component", events)
        self.assertIn('"generated"', events)

    def test_warmup_resolves_registry(self):
        """Warmup must fill the same key live traffic reads, or the warmed
        cache is dead weight and every real request is a cold miss."""
        self._upsert()
        warmup = zone_router.ZoneWarmupRequest(zones=[self._request()])
        asyncio.run(zone_router.warmup_zones(warmup, self.ADMIN))
        self.assertEqual(len(self.rendered_requests), 1)

        response = asyncio.run(
            zone_router._handle_render(
                self._request(base_prompt="different props"), self.CLIENT
            )
        )
        self.assertEqual(len(self.rendered_requests), 1)  # served warm, no new call
        self.assertEqual(response.meta["cache"]["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
