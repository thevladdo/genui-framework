"""
Tests for the per-tenant theme store.

The invariants:
- a theme saved for a tenant reads back identically (that is the whole
  point: the theme has a home instead of a copy-pasted snippet);
- the token whitelist is the contract in both directions - a value that
  could inject CSS is refused on write, and a blob that got into the
  store some other way is refused on read;
- unset tokens stay absent, so a saved theme means the same thing as the
  Playground export ("library default wins"), never "override with empty";
- nothing crosses tenants, on read or on write.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The router tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import unittest

from pydantic import ValidationError

import utils.theme_store as ts
from utils.theme_store import TenantTheme, ThemeStore

try:
    import api.theme_router as theme_router
    import auth.dependencies as auth_deps
    from auth.keys import AuthContext

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


def run(coro):
    return asyncio.run(coro)


FULL_THEME = {
    "mode": "light",
    "borderRadius": "24px",
    "radiusSm": "12px",
    "radiusLg": "32px",
    "radiusFull": "999px",
    "glassBlur": "20px",
    "spacingScale": "lg",
    "accentColor": "#3b82f6",
    "fontFamily": "'Inter', system-ui, sans-serif",
    "fontWeightHeading": "700",
    "successColor": "#22c55e",
    "errorColor": "#ef4444",
    "surface1": "#0a0a0c",
    "surface2": "#121216",
    "surface3": "#1a1a20",
    "textOnAccent": "#ffffff",
    "disclosureEnabled": "on",
    "disclosurePosition": "below-right",
    "disclosureText": "Contenuto generato con AI",
    "disclosureFontSize": "13px",
    "disclosureOpacity": "0.8",
}


class TestContract(unittest.TestCase):
    """The whitelist mirrored from studio/src/lib/theme.ts."""

    def test_full_playground_theme_is_accepted(self):
        self.assertEqual(TenantTheme(**FULL_THEME).tokens(), FULL_THEME)

    def test_unset_tokens_stay_absent(self):
        tokens = TenantTheme(accentColor="#ff0000").tokens()
        self.assertEqual(tokens, {"accentColor": "#ff0000"})

    def test_unknown_token_is_refused(self):
        with self.assertRaises(ValidationError):
            TenantTheme(**{**FULL_THEME, "backgroundImage": "url(x)"})

    def test_css_injection_is_refused(self):
        # Each of these would break out of the custom property value it
        # lands in, or reach out over the network from a stylesheet.
        for key, value in [
            ("accentColor", "red; background: url(//evil.test/x)"),
            ("borderRadius", "24px; position: fixed"),
            ("fontFamily", "Inter, url(//evil.test/f.woff)"),
            ("fontFamily", "Inter; } body { display: none"),
            ("mode", "dark; color: red"),
            ("spacingScale", "base) var(--x"),
            ("fontWeightHeading", "700; content: 'x'"),
            ("successColor", "#22c55e; background: url(//evil.test/x)"),
        ]:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValidationError):
                    TenantTheme(**{key: value})

    def test_disclosure_notice_cannot_be_styled_into_invisibility(self):
        """
        The notice is a transparency obligation: it can be made smaller
        or fainter, never unreadable. The floors live in the contract so
        a hand-written PUT cannot go under them either.
        """
        for key, value in [
            ("disclosureFontSize", "4px"),
            ("disclosureFontSize", "10px"),
            ("disclosureFontSize", "48px"),
            ("disclosureOpacity", "0"),
            ("disclosureOpacity", "0.1"),
            ("disclosureOpacity", "0.59"),
            ("disclosureEnabled", "maybe"),
            ("disclosurePosition", "floating"),
            ("disclosurePosition", "top"),
            ("disclosurePosition", "left"),
            ("disclosurePosition", "above-left; opacity: 0"),
            ("disclosureOpacity", "1; visibility: hidden"),
            ("disclosureFontSize", "12px; opacity: 0"),
        ]:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValidationError):
                    TenantTheme(**{key: value})

    def test_disclosure_edges_of_the_contract_pass(self):
        for key, value in [
            ("disclosureFontSize", "11px"),
            ("disclosureFontSize", "24px"),
            ("disclosureOpacity", "0.6"),
            ("disclosureOpacity", "1"),
            ("disclosureOpacity", "1.0"),
            ("disclosureEnabled", "off"),
            ("disclosurePosition", "above-center"),
            ("disclosurePosition", "above-right"),
            ("disclosurePosition", "below-left"),
        ]:
            with self.subTest(key=key, value=value):
                self.assertEqual(TenantTheme(**{key: value}).tokens(), {key: value})

    def test_disclosure_wording_is_bounded_text(self):
        self.assertEqual(
            TenantTheme(disclosureText="Testo <b>libero</b> & simboli").tokens(),
            {"disclosureText": "Testo <b>libero</b> & simboli"},
        )
        with self.assertRaises(ValidationError):
            TenantTheme(disclosureText="x" * 121)

    def test_inherit_font_and_square_brand_pass(self):
        tokens = TenantTheme(fontFamily="inherit", radiusFull="0px").tokens()
        self.assertEqual(tokens, {"fontFamily": "inherit", "radiusFull": "0px"})


class TestStore(unittest.TestCase):
    """Pure store semantics (in-memory backend, no Redis)."""

    def setUp(self):
        self.store = ThemeStore()

    def test_set_get_roundtrip(self):
        run(self.store.set("acme", TenantTheme(**FULL_THEME)))
        record = run(self.store.get("acme"))
        self.assertEqual(record["theme"], FULL_THEME)
        self.assertTrue(record["updated_at"])

    def test_missing_tenant_is_none(self):
        self.assertIsNone(run(self.store.get("nobody")))

    def test_tenant_isolation(self):
        run(self.store.set("acme", TenantTheme(accentColor="#111111")))
        self.assertIsNone(run(self.store.get("globex")))

    def test_save_replaces_previous_theme(self):
        run(self.store.set("acme", TenantTheme(**FULL_THEME)))
        run(self.store.set("acme", TenantTheme(accentColor="#00ff00")))
        self.assertEqual(
            run(self.store.get("acme"))["theme"], {"accentColor": "#00ff00"}
        )

    def test_out_of_contract_blob_in_storage_is_not_served(self):
        # Redis is shared infrastructure and this value crosses back into a
        # browser as CSS: a blob that did not come through the API is not
        # trusted just because it is in the store.
        self.store._store._memory["acme"] = {
            "theme": {"accentColor": "red; background: url(//evil.test/x)"},
            "updated_at": "2026-07-26T00:00:00+00:00",
        }
        self.assertIsNone(run(self.store.get("acme")))

    def test_garbage_document_is_not_served(self):
        self.store._store._memory["acme"] = {"nope": True}
        self.assertIsNone(run(self.store.get("acme")))

    def test_storage_backend_reports_memory_without_redis(self):
        self.assertEqual(run(self.store.storage_backend()), "memory")


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestEndpoints(unittest.TestCase):
    """Admin write, client read: tenant from the key, audited, isolated."""

    def setUp(self):
        self._saved_store = ts._STORE
        ts._STORE = ThemeStore()
        self._saved_audit = auth_deps._audit_logger

        self.events = []
        test = self

        class _RecordingAudit:
            def log(self, event, tenant, user_id=None, **payload):
                test.events.append({"event": event, "tenant": tenant, **payload})

        auth_deps._audit_logger = _RecordingAudit()

        self.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")
        self.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
        self.GLOBEX = AuthContext(tenant="globex", is_admin=True, key_fingerprint="gfp")

    def tearDown(self):
        ts._STORE = self._saved_store
        auth_deps._audit_logger = self._saved_audit

    def _put(self, auth, theme):
        return run(
            theme_router.set_theme(
                theme_router.ThemeWrite(theme=TenantTheme(**theme)), auth
            )
        )

    def test_put_then_client_get(self):
        written = self._put(self.ADMIN, FULL_THEME)
        self.assertEqual(written["theme"], FULL_THEME)
        self.assertIn(written["storage"], ("redis", "memory"))
        # The host page reads with its client key, not an admin key
        got = run(theme_router.get_theme(self.CLIENT))
        self.assertEqual(got["theme"], FULL_THEME)
        self.assertEqual(got["updated_at"], written["updated_at"])

    def test_get_without_saved_theme_is_null(self):
        got = run(theme_router.get_theme(self.CLIENT))
        self.assertIsNone(got["theme"])
        self.assertIsNone(got["updated_at"])

    def test_put_is_audited(self):
        self._put(self.ADMIN, {"accentColor": "#123456", "mode": "light"})
        changes = [e for e in self.events if e["event"] == "theme_change"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["tenant"], "acme")
        self.assertEqual(changes[0]["key"], "afp")  # who: the admin key fingerprint
        self.assertEqual(changes[0]["token_count"], 2)

    def test_no_cross_tenant_read_or_write(self):
        self._put(self.ADMIN, {"accentColor": "#123456"})
        self.assertIsNone(run(theme_router.get_theme(self.GLOBEX))["theme"])
        self._put(self.GLOBEX, {"accentColor": "#654321"})
        self.assertEqual(
            run(theme_router.get_theme(self.ADMIN))["theme"],
            {"accentColor": "#123456"},
        )

    def test_write_body_refuses_unknown_token(self):
        with self.assertRaises(ValidationError):
            theme_router.ThemeWrite(theme={"backgroundImage": "url(x)"})


if __name__ == "__main__":
    unittest.main()
