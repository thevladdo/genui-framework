"""
Tests for API key parsing and authentication logic.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from auth.keys import DEFAULT_TENANT, KeyRegistry, fingerprint, parse_key_entries


class TestParseKeyEntries(unittest.TestCase):
    def test_comma_separated_string(self):
        parsed = parse_key_entries("pk_abc:acme, pk_def:globex ,pk_ghi")
        self.assertEqual(parsed, {
            "pk_abc": "acme",
            "pk_def": "globex",
            "pk_ghi": DEFAULT_TENANT,
        })

    def test_list_input(self):
        parsed = parse_key_entries(["pk_abc:acme", "pk_def"])
        self.assertEqual(parsed["pk_abc"], "acme")
        self.assertEqual(parsed["pk_def"], DEFAULT_TENANT)

    def test_empty_inputs(self):
        self.assertEqual(parse_key_entries(None), {})
        self.assertEqual(parse_key_entries(""), {})
        self.assertEqual(parse_key_entries(" , ,"), {})

    def test_empty_tenant_defaults(self):
        parsed = parse_key_entries("pk_abc:")
        self.assertEqual(parsed["pk_abc"], DEFAULT_TENANT)


class TestKeyRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = KeyRegistry(
            client_keys="pk_client:acme",
            admin_keys="sk_admin:acme",
        )

    def test_disabled_when_no_keys(self):
        self.assertFalse(KeyRegistry().enabled)
        self.assertTrue(self.registry.enabled)

    def test_client_key_authenticates(self):
        ctx = self.registry.authenticate("pk_client")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.tenant, "acme")
        self.assertFalse(ctx.is_admin)

    def test_admin_key_authenticates_as_admin(self):
        ctx = self.registry.authenticate("sk_admin")
        self.assertTrue(ctx.is_admin)
        self.assertEqual(ctx.tenant, "acme")

    def test_unknown_key_rejected(self):
        self.assertIsNone(self.registry.authenticate("pk_wrong"))
        self.assertIsNone(self.registry.authenticate(None))
        self.assertIsNone(self.registry.authenticate(""))

    def test_key_with_whitespace_trimmed(self):
        ctx = self.registry.authenticate("  pk_client  ")
        self.assertIsNotNone(ctx)

    def test_fingerprint_never_exposes_key(self):
        ctx = self.registry.authenticate("pk_client")
        self.assertNotIn("pk_client", ctx.key_fingerprint)
        self.assertEqual(len(ctx.key_fingerprint), 12)
        # Deterministic
        self.assertEqual(ctx.key_fingerprint, fingerprint("pk_client"))

    def test_overlapping_key_treated_as_admin(self):
        registry = KeyRegistry(client_keys="key1:a", admin_keys="key1:b")
        ctx = registry.authenticate("key1")
        self.assertTrue(ctx.is_admin)


if __name__ == "__main__":
    unittest.main()
