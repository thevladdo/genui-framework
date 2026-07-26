"""
Tests for zone config governance: the draft/approved
workflow on top of the S1 registry, the observed zone catalog, and the
admin CRUD endpoints.

The invariants:
- saving a draft NEVER touches what production serves (the approved
  record); only an explicit approval does;
- preview_draft renders the draft for admins only and never writes the
  cache real traffic reads;
- the backend collects every (tenant, zone_id) it actually serves, so
  the Studio can list zones that exist in the host site but not yet in
  the registry (ungoverned);
- tenants never see each other's configs or observed zones;
- every state transition is audit-logged with who did it.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The router/endpoint tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import unittest

import zones.registry as registry_module
from zones import (
    STATUS_APPROVED,
    STATUS_DRAFT,
    VersionConflict,
    ZoneConfigStore,
)

try:
    import api.deps as deps
    import api.zone_config_router as config_router
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from auth.keys import AuthContext
    from config import settings
    from fastapi import HTTPException
    from utils.rate_limit import RateLimiter
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


APPROVED_CONFIG = {"base_prompt": "APPROVED prompt, serving in production"}
DRAFT_CONFIG = {"base_prompt": "DRAFT prompt, marketing is still editing"}


def run(coro):
    return asyncio.run(coro)


class TestDraftApprovedWorkflow(unittest.TestCase):
    """Pure store semantics: drafts live beside the approved record."""

    def setUp(self):
        self.store = ZoneConfigStore()

    def test_save_draft_preserves_approved(self):
        """THE regression that made governance impractical: editing must
        not overwrite (and silently un-serve) the approved config."""
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))

        approved = run(self.store.get_approved("acme", "hero"))
        self.assertIsNotNone(approved)
        self.assertEqual(
            approved["config"]["base_prompt"], APPROVED_CONFIG["base_prompt"]
        )
        draft = run(self.store.get_draft("acme", "hero"))
        self.assertEqual(draft["status"], STATUS_DRAFT)
        self.assertEqual(draft["config"]["base_prompt"], DRAFT_CONFIG["base_prompt"])

    def test_version_spans_draft_and_approved(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))  # v1
        draft = run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))
        self.assertEqual(draft["version"], 2)

        approved = run(self.store.approve("acme", "hero"))
        self.assertEqual(approved["version"], 2)
        self.assertEqual(approved["status"], STATUS_APPROVED)
        self.assertIsNone(run(self.store.get_draft("acme", "hero")))

        draft = run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))
        self.assertEqual(draft["version"], 3)

    def test_approve_serves_the_draft_config(self):
        run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))
        run(self.store.approve("acme", "hero"))
        approved = run(self.store.get_approved("acme", "hero"))
        self.assertEqual(approved["config"]["base_prompt"], DRAFT_CONFIG["base_prompt"])

    def test_approve_without_draft_returns_none(self):
        self.assertIsNone(run(self.store.approve("acme", "hero")))

    def test_approve_legacy_main_slot_draft(self):
        """Phase-1 drafts were written to the main slot via upsert(status=draft):
        approving must still work on them."""
        run(self.store.upsert("acme", "hero", dict(DRAFT_CONFIG), status=STATUS_DRAFT))
        approved = run(self.store.approve("acme", "hero"))
        self.assertEqual(approved["status"], STATUS_APPROVED)
        self.assertIsNotNone(run(self.store.get_approved("acme", "hero")))

    def test_discard_draft(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))
        self.assertTrue(run(self.store.discard_draft("acme", "hero")))
        self.assertIsNone(run(self.store.get_draft("acme", "hero")))
        # the approved record is untouched
        self.assertIsNotNone(run(self.store.get_approved("acme", "hero")))
        self.assertFalse(run(self.store.discard_draft("acme", "hero")))

    def test_delete_removes_draft_too(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))
        self.assertTrue(run(self.store.delete("acme", "hero")))
        self.assertIsNone(run(self.store.get("acme", "hero")))
        self.assertIsNone(run(self.store.get_draft("acme", "hero")))

    def test_expected_version_conflict(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        with self.assertRaises(VersionConflict):
            run(
                self.store.save_draft(
                    "acme", "hero", dict(DRAFT_CONFIG), expected_version=99
                )
            )
        # matching version writes
        draft = run(
            self.store.save_draft(
                "acme", "hero", dict(DRAFT_CONFIG), expected_version=1
            )
        )
        self.assertEqual(draft["version"], 2)
        with self.assertRaises(VersionConflict):
            run(self.store.approve("acme", "hero", expected_version=1))
        approved = run(self.store.approve("acme", "hero", expected_version=2))
        self.assertEqual(approved["version"], 2)

    def test_draft_tenant_isolation(self):
        run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))
        self.assertIsNone(run(self.store.get_draft("globex", "hero")))
        self.assertIsNone(run(self.store.approve("globex", "hero")))


class TestZoneCatalog(unittest.TestCase):
    """Observed zones + registry listing, per tenant."""

    def setUp(self):
        self.store = ZoneConfigStore()

    def test_list_zones_statuses(self):
        run(self.store.upsert("acme", "approved-only", dict(APPROVED_CONFIG)))
        run(self.store.save_draft("acme", "draft-only", dict(DRAFT_CONFIG)))
        run(self.store.upsert("acme", "both", dict(APPROVED_CONFIG)))
        run(self.store.save_draft("acme", "both", dict(DRAFT_CONFIG)))

        listed = run(self.store.list_zones("acme"))
        self.assertEqual(listed["approved-only"]["status"], STATUS_APPROVED)
        self.assertFalse(listed["approved-only"]["has_draft"])
        self.assertEqual(listed["draft-only"]["status"], STATUS_DRAFT)
        self.assertTrue(listed["draft-only"]["has_draft"])
        self.assertEqual(listed["both"]["status"], STATUS_APPROVED)
        self.assertTrue(listed["both"]["has_draft"])
        self.assertEqual(listed["both"]["version"], 2)  # the draft is the latest edit

    def test_list_zones_tenant_isolation(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        self.assertEqual(run(self.store.list_zones("globex")), {})

    def test_observed_recorded_and_isolated(self):
        run(self.store.record_observed("acme", "hero"))
        run(self.store.record_observed("acme", "hero"))  # logical identity: no dup
        run(self.store.record_observed("acme", "sidebar"))
        self.assertEqual(run(self.store.observed("acme")), {"hero", "sidebar"})
        self.assertEqual(run(self.store.observed("globex")), set())

    def test_observed_capped(self):
        """zone_id comes from a public pk_ request body: the set must not
        be a memory-growth vector for an attacker sending random ids."""
        original = registry_module._OBSERVED_MAX
        registry_module._OBSERVED_MAX = 3
        try:
            for i in range(10):
                run(self.store.record_observed("acme", f"zone-{i}"))
            self.assertEqual(len(run(self.store.observed("acme"))), 3)
        finally:
            registry_module._OBSERVED_MAX = original


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class GovernanceRouterBase(unittest.TestCase):
    """Shared harness: fresh stores/caches, fake renderer, recorded audit."""

    @classmethod
    def setUpClass(cls):
        cls.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
        cls.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")
        cls.GLOBEX_ADMIN = AuthContext(
            tenant="globex", is_admin=True, key_fingerprint="gfp"
        )

    def setUp(self):
        self._saved = (
            zone_router._zone_cache,
            zone_router._llm_budget,
            deps._zone_config_store,
            auth_deps._rate_limiter,
            auth_deps._audit_logger,
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

        self.audit_events = []
        store_test = self

        class _RecordingAudit:
            def log(self, event, tenant, user_id=None, **payload):
                store_test.audit_events.append(
                    {"event": event, "tenant": tenant, **payload}
                )

        auth_deps._audit_logger = _RecordingAudit()

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
                "rendered_at": "2026-07-23T00:00:00+00:00",
            }

        zone_router._render_live = fake_render

    def tearDown(self):
        zone_router._render_live = self._orig_render
        (
            zone_router._zone_cache,
            zone_router._llm_budget,
            deps._zone_config_store,
            auth_deps._rate_limiter,
            auth_deps._audit_logger,
            settings.llm_budget_per_hour,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
        ) = self._saved

    def _render_request(self, zone_id="hero", **kwargs):
        kwargs.setdefault("base_prompt", "HOST PROPS prompt")
        return zone_router.ZoneRenderRequest(zone_id=zone_id, **kwargs)

    def _write_body(self, **kwargs):
        kwargs.setdefault("base_prompt", DRAFT_CONFIG["base_prompt"])
        return config_router.ZoneConfigWrite(**kwargs)


class TestGovernanceEndpoints(GovernanceRouterBase):
    def test_draft_via_api_not_served_until_approved(self):
        run(
            config_router.save_zone_draft(self._write_body(), "hero", self.ADMIN)
        )
        run(zone_router._handle_render(self._render_request(), self.CLIENT))
        self.assertEqual(self.rendered_requests[0].base_prompt, "HOST PROPS prompt")

        run(config_router.approve_zone_config("hero", None, self.ADMIN))
        run(
            zone_router._handle_render(
                self._render_request(base_prompt="other props"), self.CLIENT
            )
        )
        self.assertEqual(
            self.rendered_requests[1].base_prompt, DRAFT_CONFIG["base_prompt"]
        )

    def test_list_unions_registry_and_observed(self):
        # a real client render makes the zone observed (segment strategy)
        run(zone_router._handle_render(self._render_request("observed-zone"), self.CLIENT))
        run(
            config_router.save_zone_draft(
                self._write_body(), "governed-zone", self.ADMIN
            )
        )

        listing = run(config_router.list_zone_configs(self.ADMIN))
        by_id = {z["zone_id"]: z for z in listing["zones"]}
        self.assertEqual(by_id["observed-zone"]["status"], "ungoverned")
        self.assertTrue(by_id["observed-zone"]["observed"])
        self.assertEqual(by_id["governed-zone"]["status"], STATUS_DRAFT)
        self.assertFalse(by_id["governed-zone"]["observed"])

        # another tenant sees none of this
        globex = run(config_router.list_zone_configs(self.GLOBEX_ADMIN))
        self.assertEqual(globex["zones"], [])

    def test_observed_on_cached_render_not_on_admin_live(self):
        run(zone_router._handle_render(self._render_request("real-zone"), self.CLIENT))
        run(
            zone_router._handle_render(
                self._render_request("adhoc-preview", cache_strategy="live"),
                self.ADMIN,
            )
        )
        self.assertEqual(run(self.store.observed("acme")), {"real-zone"})

    def test_state_transitions_are_audited(self):
        run(config_router.save_zone_draft(self._write_body(), "hero", self.ADMIN))
        run(config_router.approve_zone_config("hero", None, self.ADMIN))
        run(config_router.delete_zone_config("hero", self.ADMIN))

        changes = [e for e in self.audit_events if e["event"] == "zone_config_change"]
        self.assertEqual(
            [c["action"] for c in changes], ["draft_saved", "approved", "deleted"]
        )
        for change in changes:
            self.assertEqual(change["tenant"], "acme")
            self.assertEqual(change["key"], "afp")  # who: the admin key fingerprint
            self.assertEqual(change["zone_id"], "hero")

    def test_approve_without_draft_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            run(config_router.approve_zone_config("hero", None, self.ADMIN))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_version_conflict_is_409(self):
        run(config_router.save_zone_draft(self._write_body(), "hero", self.ADMIN))
        with self.assertRaises(HTTPException) as ctx:
            run(
                config_router.save_zone_draft(
                    self._write_body(expected_version=99), "hero", self.ADMIN
                )
            )
        self.assertEqual(ctx.exception.status_code, 409)


class TestPreviewDraft(GovernanceRouterBase):
    def _setup_approved_and_draft(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        run(self.store.save_draft("acme", "hero", dict(DRAFT_CONFIG)))

    def test_preview_draft_renders_draft_without_caching(self):
        self._setup_approved_and_draft()
        response = run(
            zone_router._handle_render(
                self._render_request(preview_draft=True), self.ADMIN
            )
        )
        self.assertEqual(
            self.rendered_requests[0].base_prompt, DRAFT_CONFIG["base_prompt"]
        )
        self.assertEqual(response.meta["cache"]["status"], "bypass")

        # a client render right after still serves the APPROVED config,
        # and the preview left nothing for it in the cache (cold miss)
        run(zone_router._handle_render(self._render_request(), self.CLIENT))
        self.assertEqual(len(self.rendered_requests), 2)
        self.assertEqual(
            self.rendered_requests[1].base_prompt, APPROVED_CONFIG["base_prompt"]
        )

    def test_preview_draft_requires_admin(self):
        self._setup_approved_and_draft()
        with self.assertRaises(HTTPException) as ctx:
            run(
                zone_router._handle_render(
                    self._render_request(preview_draft=True), self.CLIENT
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_preview_draft_falls_back_to_approved_without_draft(self):
        run(self.store.upsert("acme", "hero", dict(APPROVED_CONFIG)))
        run(
            zone_router._handle_render(
                self._render_request(preview_draft=True), self.ADMIN
            )
        )
        self.assertEqual(
            self.rendered_requests[0].base_prompt, APPROVED_CONFIG["base_prompt"]
        )

    def test_warmup_never_caches_a_draft(self):
        """A warmup body could smuggle preview_draft=true: the warmed cache
        is what real traffic reads, so a draft must never land there."""
        self._setup_approved_and_draft()
        warmup = zone_router.ZoneWarmupRequest(
            zones=[self._render_request(preview_draft=True)]
        )
        run(zone_router.warmup_zones(warmup, self.ADMIN))
        self.assertEqual(
            self.rendered_requests[0].base_prompt, APPROVED_CONFIG["base_prompt"]
        )


if __name__ == "__main__":
    unittest.main()
