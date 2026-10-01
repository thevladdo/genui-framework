"""
State that cannot be regenerated, with Redis unreachable.

A cache that loses Redis regenerates.
A content policy, a zone approval and a profile do not: with the store unreachable the answer is the last version this process knows, or a retryable refusal, never "nothing stored".
And a write that two requests make at the same time keeps both.

Redis is the controllable fake of test_redis_reconnect, extended with WATCH/MULTI/EXEC; `server.up = False` is the outage.
"""

import asyncio
import json
import os
import tempfile
import unittest

from profiles.store import ProfileStore
from test_redis_reconnect import FakeRedisTestCase, unique_url
from utils.content_policy_store import ContentPolicyStore
from utils.redis_conn import StoreUnavailable
from zones import VersionConflict, ZoneConfigStore

try:
    from fastapi.testclient import TestClient

    import api.deps as deps
    import api.main as main
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    import utils.content_policy_store as policy_store
    from config import settings
    from memory_stores import use_memory_stores
    from utils.audit import AuditLogger
    from utils.content_policy_store import effective_policy
    from utils.rate_limit import RateLimiter
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


def run(coro):
    return asyncio.run(coro)


REGISTRY_CONFIG = {"base_prompt": "APPROVED PROMPT", "max_items": 3}


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class AppTestCase(FakeRedisTestCase):
    """Real routes over the fake Redis, keys and audit trail of a test tenant."""

    def setUp(self):
        super().setUp()
        use_memory_stores()
        audit_dir = tempfile.TemporaryDirectory(prefix="genui-audit-")
        self.addCleanup(audit_dir.cleanup)
        self.audit_path = os.path.join(audit_dir.name, "audit.jsonl")
        saved = {
            name: getattr(settings, name)
            for name in (
                "client_api_keys", "admin_api_keys", "user_token_secrets",
                "genui_dev_open", "audit_log_path", "audit_log_enabled",
                "redis_url", "llm_budget_per_hour", "zone_cache_enabled",
                "holdout_percent",
            )
        }
        self.addCleanup(lambda: [setattr(settings, k, v) for k, v in saved.items()])
        settings.client_api_keys = "pk_test:acme"
        settings.admin_api_keys = "sk_test:acme"
        settings.user_token_secrets = ""
        settings.genui_dev_open = True
        settings.audit_log_path = self.audit_path
        settings.audit_log_enabled = True
        settings.redis_url = None
        settings.llm_budget_per_hour = 0
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0

        for module, name, value in (
            (auth_deps, "_registry", None),
            (auth_deps, "_rate_limiter", RateLimiter(limit=1000, window_seconds=60)),
            (auth_deps, "_audit_logger", AuditLogger(path=self.audit_path, enabled=True)),
            (auth_deps, "_user_token_verifier", None),
            (deps, "_llm_budget", None),
            (zone_router, "_zone_cache", ZoneRenderCache()),
        ):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        self.addCleanup(auth_deps._audit_logger.close)

        self.rendered = []

        async def fake_render(request, tenant, segment=None):
            self.rendered.append(request.base_prompt)
            return {
                "render_id": f"r{len(self.rendered)}",
                "components": [
                    {"type": "text", "data": {"content": "A zero risk plan for you"}},
                    {"type": "text", "data": {"content": "Plain facts"}},
                ],
                "pinned_content_included": [],
                "personalization_applied": False,
                "meta": {},
                "rendered_at": "2026-09-27T00:00:00+00:00",
            }

        self.addCleanup(setattr, zone_router, "_render_live", zone_router._render_live)
        zone_router._render_live = fake_render
        self.client = TestClient(main.app)

    def audit_events(self, event):
        with open(self.audit_path) as f:
            return [e for e in map(json.loads, f) if e["event"] == event]

    def render(self, **body):
        body.setdefault("zone_id", "pricing")
        body.setdefault("base_prompt", "HOST PROPS PROMPT")
        return self.client.post(
            "/api/v1/zone/render", headers={"X-API-Key": "pk_test"}, json=body
        )


# (a) A saved policy outlives an outage


class TestPolicyDuringAnOutage(AppTestCase):
    def setUp(self):
        super().setUp()
        self.url = unique_url()
        policy_store._STORE = ContentPolicyStore(redis_url=self.url)

    def test_saved_term_is_still_enforced_with_redis_down(self):
        run(policy_store._STORE.set("acme", ["zero risk"]))
        self.server.up = False

        policy = run(effective_policy("acme", ""))
        self.assertIn("zero risk", policy.banned_terms)
        self.assertTrue(policy.last_known)

        response = self.render()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("zero risk", json.dumps(body["components"]))
        self.assertEqual(len(body["components"]), 1)
        self.assertTrue(body["meta"]["sanitization"]["policy_last_known"])

    def test_the_flag_clears_once_redis_answers_again(self):
        run(policy_store._STORE.set("acme", ["zero risk"]))
        self.server.up = False
        self.assertTrue(self.render().json()["meta"]["sanitization"]["policy_last_known"])

        self.server.up = True
        policy_store._STORE._store._conn._retry_at = 0.0
        body = self.render().json()
        self.assertNotIn("policy_last_known", body["meta"]["sanitization"])
        self.assertNotIn("zero risk", json.dumps(body["components"]))

    def test_a_process_that_never_read_the_policy_refuses(self):
        run(policy_store._STORE.set("acme", ["zero risk"]))
        policy_store._STORE = ContentPolicyStore(redis_url=self.url)  # fresh process
        self.server.up = False

        with self.assertRaises(StoreUnavailable):
            run(effective_policy("acme", ""))
        response = self.render()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Retry-After", response.headers)

    def test_a_process_that_only_read_the_policy_keeps_enforcing_it(self):
        """The save lands on one worker; the others know the policy because they read it."""
        run(policy_store._STORE.set("acme", ["zero risk"]))
        policy_store._STORE = ContentPolicyStore(redis_url=self.url)
        run(effective_policy("acme", ""))
        self.server.up = False

        policy = run(effective_policy("acme", ""))
        self.assertIn("zero risk", policy.banned_terms)
        self.assertTrue(policy.last_known)
        response = self.render()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("zero risk", json.dumps(response.json()["components"]))

    def test_a_page_on_another_origin_can_read_retry_after(self):
        """Retry-After is not a CORS-safelisted header: unlisted, a browser hides it from the page."""
        run(policy_store._STORE.set("acme", ["zero risk"]))
        policy_store._STORE = ContentPolicyStore(redis_url=self.url)
        self.server.up = False

        response = self.client.post(
            "/api/v1/zone/render",
            headers={"X-API-Key": "pk_test", "Origin": settings.cors_origins[0]},
            json={"zone_id": "pricing", "base_prompt": "HOST PROPS PROMPT"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("Retry-After", response.headers)
        exposed = response.headers.get("access-control-expose-headers", "")
        self.assertIn("retry-after", [h.strip().lower() for h in exposed.split(",")])

    def test_a_save_that_redis_refused_is_not_reported_saved(self):
        self.server.up = False
        response = self.client.put(
            "/api/v1/content-policy",
            headers={"X-API-Key": "sk_test"},
            json={"banned_terms": ["zero risk"]},
        )
        self.assertEqual(response.status_code, 503)


# (b) Erasure and export tell the truth


class TestErasureDuringAnOutage(AppTestCase):
    def setUp(self):
        super().setUp()
        self.store = ProfileStore(redis_url=unique_url())
        self.addCleanup(setattr, main, "get_profile_store", main.get_profile_store)
        main.get_profile_store = lambda: self.store
        run(self.store.set("acme", "alice", {"interests": {"ai": 1}}))

    def test_delete_with_redis_down_is_a_503_and_the_profile_stays(self):
        self.server.up = False
        response = self.client.delete(
            "/api/v1/profile/alice", headers={"X-API-Key": "pk_test"}
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Retry-After", response.headers)
        self.assertIn("NOT erased", response.json()["detail"])
        self.assertTrue(self.server.has_key("genui:profile:acme:alice"))
        attempts = self.audit_events("profile_delete")
        self.assertEqual([e["outcome"] for e in attempts], ["store_unavailable"])

        self.server.up = True
        self.store._conn._retry_at = 0.0
        response = self.client.delete(
            "/api/v1/profile/alice", headers={"X-API-Key": "pk_test"}
        )
        self.assertTrue(response.json()["profile_erased"])
        self.assertFalse(self.server.has_key("genui:profile:acme:alice"))
        self.assertEqual(self.audit_events("profile_delete")[-1]["outcome"], "erased")

    def test_export_and_read_do_not_answer_nothing(self):
        self.server.up = False
        headers = {"X-API-Key": "pk_test"}
        self.assertEqual(
            self.client.get("/api/v1/profile/alice/export", headers=headers).status_code, 503
        )
        self.assertEqual(
            self.client.get("/api/v1/profile/alice", headers=headers).status_code, 503
        )

    def test_nothing_is_parked_in_memory_during_an_outage(self):
        """A copy an erasure on another worker could not reach."""
        self.server.up = False
        with self.assertRaises(StoreUnavailable):
            run(self.store.sync_client_profile("acme", "bob", {"interests": {"x": 1}}))
        self.assertEqual(self.store._memory, {})


# (c) Concurrent merges of one profile keep both


class TestConcurrentProfileMerges(FakeRedisTestCase):
    def test_two_agent_updates_both_land(self):
        store = ProfileStore(redis_url=unique_url())

        async def scenario():
            await store.get("acme", "u1")  # connected, as in steady state
            await asyncio.gather(
                store.apply_updates("acme", "u1", [{"field": "interests.ai", "value": "yes", "confidence": 0.9}]),
                store.apply_updates("acme", "u1", [{"field": "preferences.role", "value": "dev", "confidence": 0.9}]),
            )
            return await store.get("acme", "u1")

        profile = run(scenario())
        self.assertEqual(profile["interests"]["ai"]["value"], "yes")
        self.assertEqual(profile["preferences"]["role"]["value"], "dev")

    def test_a_client_sync_and_an_agent_update_both_land(self):
        store = ProfileStore(redis_url=unique_url())
        client_profile = {"demographic": {"country": {"value": "IT", "confidence": 0.8}}}

        async def scenario():
            await store.get("acme", "u1")
            await asyncio.gather(
                store.sync_client_profile("acme", "u1", client_profile),
                store.apply_updates("acme", "u1", [{"field": "interests.ai", "value": "yes", "confidence": 0.9}]),
            )
            return await store.get("acme", "u1")

        profile = run(scenario())
        self.assertEqual(profile["demographic"]["country"]["value"], "IT")
        self.assertEqual(profile["interests"]["ai"]["value"], "yes")


# (d) Version-checked registry writes are atomic


class TestConcurrentRegistryWrites(FakeRedisTestCase):
    def setUp(self):
        super().setUp()
        self.store = ZoneConfigStore(redis_url=unique_url())
        self.version = run(self.store.save_draft("acme", "pricing", REGISTRY_CONFIG))["version"]

    def _settled(self, call):
        async def settle():
            try:
                return await call
            except VersionConflict:
                return "conflict"
        return settle()

    def test_two_approvals_of_one_version_one_wins(self):
        async def scenario():
            return await asyncio.gather(
                self._settled(self.store.approve("acme", "pricing", self.version)),
                self._settled(self.store.approve("acme", "pricing", self.version)),
            )

        outcomes = run(scenario())
        self.assertEqual(sum(isinstance(o, dict) for o in outcomes), 1, outcomes)

    def test_delete_over_a_newer_version_conflicts(self):
        run(self.store.approve("acme", "pricing", self.version))
        run(self.store.save_draft("acme", "pricing", {"base_prompt": "NEWER"}))
        with self.assertRaises(VersionConflict):
            run(self.store.delete("acme", "pricing", expected_version=self.version))
        self.assertIsNotNone(run(self.store.get("acme", "pricing")))


# (e) An unreadable approval never becomes the host's props


class TestRegistryDuringAnOutage(AppTestCase):
    def setUp(self):
        super().setUp()
        self.url = unique_url()
        run(ZoneConfigStore(redis_url=self.url).upsert("acme", "pricing", REGISTRY_CONFIG))

    def test_a_process_that_never_read_the_approval_refuses(self):
        deps._zone_config_store = ZoneConfigStore(redis_url=self.url)
        self.server.up = False

        response = self.render()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(self.rendered, [])

    def test_the_last_known_approval_keeps_serving(self):
        deps._zone_config_store = ZoneConfigStore(redis_url=self.url)
        self.assertEqual(self.render().status_code, 200)  # reads the approval
        self.server.up = False
        zone_router._zone_cache = ZoneRenderCache()

        self.assertEqual(self.render().status_code, 200)
        self.assertEqual(self.rendered, ["APPROVED PROMPT", "APPROVED PROMPT"])


if __name__ == "__main__":
    unittest.main()
