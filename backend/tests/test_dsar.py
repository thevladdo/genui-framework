"""
Tests for lawful basis and data subject rights.

Three rules the tests defend:
(a) no identity, no per-user state: a request nobody signed cannot
    create, seed or update a profile, and cannot store one under a
    placeholder that every anonymous visitor would share;
(b) the access export returns everything held about ONE person, behind
    the same identity guard as the other per-user routes, and nothing
    belonging to anyone else;
(c) erasure removes the profile and says out loud what it does not
    remove.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The route tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import json
import os
import tempfile
import unittest

from profiles.store import ProfileStore, is_identified

try:
    from fastapi.testclient import TestClient

    import api.main as main
    import api.deps as deps
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from api.zone_router import ZoneRenderRequest
    from auth.keys import AuthContext
    from config import settings
    from utils.audit import AuditLogger
    from utils.rate_limit import RateLimiter
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


class TestIsIdentified(unittest.TestCase):
    """What counts as a data subject, and what is just a default value."""

    def test_real_ids_are_identities(self):
        for user_id in ["u-42", "alice@example.com", "  padded-id  "]:
            self.assertTrue(is_identified(user_id), user_id)

    def test_blank_and_placeholders_are_not(self):
        for user_id in [None, "", "   ", "anonymous", "ANONYMOUS", "anon",
                        "undefined", "null", "none"]:
            self.assertFalse(is_identified(user_id), repr(user_id))


class TestStoreRefusesAnonymousWrites(unittest.TestCase):
    """The single place per-user state is born is the place that refuses."""

    def test_set_without_identity_raises(self):
        store = ProfileStore()
        for user_id in ["", "  ", "anonymous"]:
            with self.assertRaises(ValueError, msg=user_id):
                asyncio.run(store.set("acme", user_id, {"interests": {}}))

    def test_higher_level_writes_refuse_too(self):
        """sync_client_profile and apply_updates both funnel into set()."""
        store = ProfileStore()
        with self.assertRaises(ValueError):
            asyncio.run(store.sync_client_profile("acme", "anonymous", {"a": 1}))
        with self.assertRaises(ValueError):
            asyncio.run(store.apply_updates("acme", "", []))

    def test_identified_write_still_works(self):
        store = ProfileStore()
        asyncio.run(store.set("acme", "u-1", {"interests": {"ai": 1}}))
        self.assertEqual(
            asyncio.run(store.get("acme", "u-1")), {"interests": {"ai": 1}}
        )


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestAnonymousRenderCreatesNoState(unittest.TestCase):
    """The consent-denied request, seen from the server side."""

    def setUp(self):
        self.client_auth = AuthContext(
            tenant="acme", is_admin=False, key_fingerprint="cfp"
        )
        self._saved = (
            zone_router._zone_cache,
            deps._llm_budget,
            settings.zone_cache_enabled,
            settings.redis_url,
            settings.llm_budget_per_hour,
            settings.holdout_percent,
        )
        zone_router._zone_cache = ZoneRenderCache()
        deps._llm_budget = None
        settings.zone_cache_enabled = True
        settings.redis_url = None
        settings.llm_budget_per_hour = 0
        settings.holdout_percent = 0.0

        self.store = ProfileStore()
        self._orig_store = zone_router.get_profile_store
        zone_router.get_profile_store = lambda: self.store

        self._orig_live = zone_router._render_live
        async def _fake_live(request, tenant, segment=None):
            return {
                "render_id": "r1",
                "components": [{"type": "text", "data": {"content": "hello"}}],
                "pinned_content_included": [],
                "personalization_applied": False,
                "meta": {},
                "rendered_at": "2026-07-27T00:00:00+00:00",
            }
        zone_router._render_live = _fake_live

    def tearDown(self):
        zone_router.get_profile_store = self._orig_store
        zone_router._render_live = self._orig_live
        (
            zone_router._zone_cache,
            deps._llm_budget,
            settings.zone_cache_enabled,
            settings.redis_url,
            settings.llm_budget_per_hour,
            settings.holdout_percent,
        ) = self._saved

    def _render(self, **kwargs):
        request = ZoneRenderRequest(
            zone_id="zone-1", base_prompt="show something", **kwargs
        )
        response = asyncio.run(
            zone_router._handle_render(request, self.client_auth)
        )
        return request, response

    def test_no_user_id_stores_nothing_and_still_renders(self):
        request, response = self._render(
            user_profile={"interests": {"crypto": {"value": True, "confidence": 1}}}
        )
        self.assertTrue(response.components)
        self.assertEqual(self.store._memory, {})

    def test_placeholder_user_id_creates_no_profile(self):
        """A client that sends its 'anonymous' default is not a person."""
        request, response = self._render(
            user_id="anonymous",
            user_profile={"interests": {"crypto": {"value": True, "confidence": 1}}},
        )
        self.assertTrue(response.components)
        self.assertEqual(self.store._memory, {})
        self.assertIsNone(request.user_id)

    def test_anonymous_request_is_served_the_anon_segment(self):
        """Degraded, not switched off: the archetype path renders it."""
        _, response = self._render()
        self.assertEqual(response.meta["cache"]["segment"], "anon")


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestDataSubjectRoutes(unittest.TestCase):
    """Access and erasure over HTTP, with the real identity guard."""

    def setUp(self):
        self.audit_path = os.path.join(
            tempfile.mkdtemp(prefix="genui-audit-"), "audit.jsonl"
        )
        self._saved = (
            settings.client_api_keys,
            settings.admin_api_keys,
            settings.user_token_secrets,
            settings.genui_dev_open,
            settings.audit_log_path,
            settings.audit_log_enabled,
            settings.redis_url,
            auth_deps._registry,
            auth_deps._rate_limiter,
            auth_deps._audit_logger,
            auth_deps._user_token_verifier,
        )
        settings.client_api_keys = "pk_test:acme"
        settings.admin_api_keys = "sk_test:acme"
        settings.user_token_secrets = ""
        settings.genui_dev_open = True  # no signing secret: the guard opens
        settings.audit_log_path = self.audit_path
        settings.audit_log_enabled = True
        settings.redis_url = None
        auth_deps._registry = None
        auth_deps._rate_limiter = RateLimiter(limit=1000, window_seconds=60)
        auth_deps._audit_logger = AuditLogger(path=self.audit_path, enabled=True)
        auth_deps._user_token_verifier = None

        self.store = ProfileStore()
        self._orig_store = main.get_profile_store
        main.get_profile_store = lambda: self.store

        asyncio.run(self.store.set("acme", "alice", {"interests": {"ai": 1}}))
        auth_deps._audit_logger.log(
            "zone_render", tenant="acme", user_id="alice", zone_id="home"
        )
        auth_deps._audit_logger.log(
            "zone_render", tenant="acme", user_id="bob", zone_id="home"
        )
        auth_deps._audit_logger.log(
            "zone_render", tenant="other", user_id="alice", zone_id="home"
        )

        self.client = TestClient(main.app)

    def tearDown(self):
        main.get_profile_store = self._orig_store
        (
            settings.client_api_keys,
            settings.admin_api_keys,
            settings.user_token_secrets,
            settings.genui_dev_open,
            settings.audit_log_path,
            settings.audit_log_enabled,
            settings.redis_url,
            auth_deps._registry,
            auth_deps._rate_limiter,
            auth_deps._audit_logger,
            auth_deps._user_token_verifier,
        ) = self._saved

    def _get(self, path, key="pk_test", token=None):
        headers = {"X-API-Key": key}
        if token:
            headers["X-User-Token"] = token
        return self.client.get(path, headers=headers)

    def test_export_returns_profile_and_own_audit_entries(self):
        body = self._get("/api/v1/profile/alice/export").json()
        self.assertEqual(body["profile"], {"interests": {"ai": 1}})
        self.assertTrue(body["audit"]["queryable"])
        users = {entry["user_id"] for entry in body["audit"]["entries"]}
        self.assertEqual(users, {"alice"})
        tenants = {entry["tenant"] for entry in body["audit"]["entries"]}
        self.assertEqual(tenants, {"acme"})

    def test_export_never_leaks_another_user(self):
        body = self._get("/api/v1/profile/bob/export").json()
        self.assertIsNone(body["profile"])
        for entry in body["audit"]["entries"]:
            self.assertEqual(entry["user_id"], "bob")

    def test_export_refused_without_a_valid_identity(self):
        """A signing secret is configured: the token now has to prove it."""
        settings.user_token_secrets = "s3cret:acme"
        auth_deps._user_token_verifier = None
        self.assertEqual(self._get("/api/v1/profile/alice/export").status_code, 403)

        from auth.identity import sign_user_token

        wrong = sign_user_token("s3cret", "bob", "acme")
        self.assertEqual(
            self._get("/api/v1/profile/alice/export", token=wrong).status_code, 403
        )
        right = sign_user_token("s3cret", "alice", "acme")
        self.assertEqual(
            self._get("/api/v1/profile/alice/export", token=right).status_code, 200
        )

    def test_erasure_removes_the_profile_and_declares_what_it_keeps(self):
        response = self.client.delete(
            "/api/v1/profile/alice", headers={"X-API-Key": "pk_test"}
        )
        body = response.json()
        self.assertTrue(body["existed"])
        self.assertTrue(body["profile_erased"])
        self.assertTrue(body["audit_retained"])
        self.assertIsNone(asyncio.run(self.store.get("acme", "alice")))

        # The trail keeps the old entries AND records the erasure, so a
        # later export shows when the right was exercised.
        after = self._get("/api/v1/profile/alice/export").json()
        self.assertIsNone(after["profile"])
        events = [entry["event"] for entry in after["audit"]["entries"]]
        self.assertIn("profile_delete", events)
        self.assertIn("zone_render", events)

    def test_sync_refuses_a_placeholder_identity(self):
        response = self.client.post(
            "/api/v1/profile/sync",
            headers={"X-API-Key": "pk_test"},
            json={"user_id": "anonymous", "profile_data": {"interests": {}}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("genui:profile:acme:anonymous", self.store._memory)

    def test_audit_file_holds_the_export_event(self):
        self._get("/api/v1/profile/alice/export")
        with open(self.audit_path, encoding="utf-8") as f:
            events = [json.loads(line)["event"] for line in f if line.strip()]
        self.assertIn("profile_export", events)


if __name__ == "__main__":
    unittest.main()
