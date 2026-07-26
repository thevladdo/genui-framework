"""
Tests for per-tenant content policy governance.

The invariants:
- a policy written for a tenant is enforced downstream (a component with
  the stored term is dropped, chat text redacted) - same behavior as the
  env source, just live and per-tenant;
- the env "*" and env per-tenant entries still merge exactly as before
  (policy_for is untouched), and stored terms add on top;
- a tenant never writes (or reads) another tenant's policy;
- the admin endpoints write the tenant from the key and audit the change.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The router tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import json
import unittest

import utils.content_policy_store as cps
from utils.content_policy_store import ContentPolicyStore, effective_policy

try:
    import api.content_policy_router as policy_router
    import auth.dependencies as auth_deps
    from auth.keys import AuthContext
    from config import settings

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


def run(coro):
    return asyncio.run(coro)


class TestStore(unittest.TestCase):
    """Pure store semantics (in-memory backend, no Redis)."""

    def setUp(self):
        self.store = ContentPolicyStore()

    def test_set_get_roundtrip(self):
        run(self.store.set("acme", ["Free Money", "guaranteed returns"]))
        self.assertEqual(
            run(self.store.get("acme")), ["Free Money", "guaranteed returns"]
        )

    def test_normalize_strips_and_dedups(self):
        run(self.store.set("acme", ["  spam ", "spam", "", "rival"]))
        self.assertEqual(run(self.store.get("acme")), ["spam", "rival"])

    def test_missing_tenant_is_empty(self):
        self.assertEqual(run(self.store.get("nobody")), [])

    def test_tenant_isolation(self):
        run(self.store.set("acme", ["secret"]))
        self.assertEqual(run(self.store.get("globex")), [])


class TestEffectivePolicy(unittest.TestCase):
    """effective_policy = env (policy_for, unchanged) + stored terms."""

    def setUp(self):
        self._saved = cps._STORE
        cps._STORE = ContentPolicyStore()

    def tearDown(self):
        cps._STORE = self._saved

    def test_stored_policy_applied_downstream(self):
        run(cps._STORE.set("acme", ["guaranteed returns"]))
        policy = run(effective_policy("acme", ""))  # no env source at all
        kept, violations = policy.sanitize_components(
            [{"type": "text", "data": {"content": "we offer guaranteed returns"}}]
        )
        self.assertEqual(kept, [])
        self.assertIn("guaranteed returns", violations)

    def test_env_star_and_tenant_merge_plus_store(self):
        env = json.dumps(
            {"*": {"banned_terms": ["spam"]}, "acme": {"banned_terms": ["rival"]}}
        )
        run(cps._STORE.set("acme", ["stored-term"]))
        terms = run(effective_policy("acme", env)).banned_terms
        self.assertIn("spam", terms)  # env "*"
        self.assertIn("rival", terms)  # env per-tenant
        self.assertIn("stored-term", terms)  # store

    def test_no_cross_tenant_leak(self):
        env = json.dumps(
            {"*": {"banned_terms": ["spam"]}, "acme": {"banned_terms": ["rival"]}}
        )
        run(cps._STORE.set("acme", ["acme-only"]))
        gterms = run(effective_policy("globex", env)).banned_terms
        self.assertIn("spam", gterms)  # env "*" is shared by design
        self.assertNotIn("rival", gterms)  # acme's env-tenant term stays acme's
        self.assertNotIn("acme-only", gterms)  # acme's stored term stays acme's

    def test_empty_store_matches_env_only(self):
        env = json.dumps({"acme": {"banned_terms": ["x", "y"]}})
        self.assertEqual(
            run(effective_policy("acme", env)).banned_terms, ["x", "y"]
        )


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestEndpoints(unittest.TestCase):
    """Admin read/write: tenant from the key, audited, isolated."""

    def setUp(self):
        self._saved_store = cps._STORE
        cps._STORE = ContentPolicyStore()
        self._saved_audit = auth_deps._audit_logger
        self._saved_env = settings.content_policy
        settings.content_policy = json.dumps({"*": {"banned_terms": ["env-global"]}})

        self.events = []
        test = self

        class _RecordingAudit:
            def log(self, event, tenant, user_id=None, **payload):
                test.events.append({"event": event, "tenant": tenant, **payload})

        auth_deps._audit_logger = _RecordingAudit()

        self.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")
        self.GLOBEX = AuthContext(tenant="globex", is_admin=True, key_fingerprint="gfp")

    def tearDown(self):
        cps._STORE = self._saved_store
        auth_deps._audit_logger = self._saved_audit
        settings.content_policy = self._saved_env

    def test_put_then_get(self):
        run(
            policy_router.set_content_policy(
                policy_router.PolicyWrite(banned_terms=["rival co", "rival co", ""]),
                self.ADMIN,
            )
        )
        got = run(policy_router.get_content_policy(self.ADMIN))
        self.assertEqual(got["banned_terms"], ["rival co"])  # normalized
        self.assertIn("env-global", got["env_terms"])  # env shown read-only

    def test_put_is_audited(self):
        run(
            policy_router.set_content_policy(
                policy_router.PolicyWrite(banned_terms=["x", "y"]), self.ADMIN
            )
        )
        changes = [e for e in self.events if e["event"] == "content_policy_change"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["tenant"], "acme")
        self.assertEqual(changes[0]["key"], "afp")  # who: the admin key fingerprint
        self.assertEqual(changes[0]["term_count"], 2)

    def test_no_cross_tenant_write(self):
        run(
            policy_router.set_content_policy(
                policy_router.PolicyWrite(banned_terms=["acme-secret"]), self.ADMIN
            )
        )
        globex = run(policy_router.get_content_policy(self.GLOBEX))
        self.assertEqual(globex["banned_terms"], [])


if __name__ == "__main__":
    unittest.main()
