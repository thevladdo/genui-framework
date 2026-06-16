"""
Tests for server-side profile merge logic and store.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import asyncio
import unittest

from profiles import apply_profile_updates, merge_client_profile
from profiles.store import ProfileStore


def run(coro):
    return asyncio.run(coro)


class TestApplyProfileUpdates(unittest.TestCase):
    def test_new_fields_added(self):
        profile = apply_profile_updates({}, [
            {"field": "interests.ai", "value": True, "confidence": 0.8},
            {"field": "preferences.role", "value": "developer", "confidence": 0.9},
        ])
        self.assertEqual(profile["interests"]["ai"]["value"], True)
        self.assertEqual(profile["preferences"]["role"]["confidence"], 0.9)
        self.assertIn("updated_at", profile["interests"]["ai"])

    def test_higher_confidence_wins(self):
        base = {"preferences": {"role": {"value": "student", "confidence": 0.6}}}
        updated = apply_profile_updates(base, [
            {"field": "preferences.role", "value": "developer", "confidence": 0.9},
        ])
        self.assertEqual(updated["preferences"]["role"]["value"], "developer")

    def test_lower_confidence_does_not_overwrite(self):
        base = {"preferences": {"role": {"value": "developer", "confidence": 0.9}}}
        updated = apply_profile_updates(base, [
            {"field": "preferences.role", "value": "student", "confidence": 0.3},
        ])
        self.assertEqual(updated["preferences"]["role"]["value"], "developer")

    def test_malformed_updates_skipped(self):
        profile = apply_profile_updates({}, [
            {"field": "no_dot", "value": 1, "confidence": 0.9},
            {"field": "a.b.c", "value": 1, "confidence": 0.9},
            {"field": "interests.x", "value": None, "confidence": 0.9},
            "not a dict",
            {"field": "interests.ok", "value": "yes", "confidence": 0.9},
        ])
        self.assertEqual(list(profile.get("interests", {}).keys()), ["ok"])
        self.assertNotIn("no_dot", profile)

    def test_input_not_mutated(self):
        base = {"interests": {"a": {"value": 1, "confidence": 0.5}}}
        apply_profile_updates(base, [
            {"field": "interests.b", "value": 2, "confidence": 0.5},
        ])
        self.assertNotIn("b", base["interests"])


class TestMergeClientProfile(unittest.TestCase):
    def test_server_wins_on_equal_confidence(self):
        server = {"preferences": {"role": {"value": "developer", "confidence": 0.8}}}
        client = {"preferences": {"role": {"value": "student", "confidence": 0.8}}}
        merged = merge_client_profile(server, client)
        self.assertEqual(merged["preferences"]["role"]["value"], "developer")

    def test_client_fills_gaps(self):
        server = {"preferences": {}}
        client = {"interests": {"ai": {"value": True, "confidence": 0.7}}}
        merged = merge_client_profile(server, client)
        self.assertEqual(merged["interests"]["ai"]["value"], True)

    def test_client_higher_confidence_wins(self):
        server = {"interests": {"ai": {"value": False, "confidence": 0.2}}}
        client = {"interests": {"ai": {"value": True, "confidence": 0.9}}}
        merged = merge_client_profile(server, client)
        self.assertEqual(merged["interests"]["ai"]["value"], True)

    def test_none_inputs(self):
        self.assertEqual(merge_client_profile(None, None), {})
        merged = merge_client_profile(None, {"interests": {"a": {"value": 1, "confidence": 1}}})
        self.assertIn("interests", merged)


class TestProfileStore(unittest.TestCase):
    def test_crud_roundtrip(self):
        store = ProfileStore()

        async def scenario():
            self.assertIsNone(await store.get("acme", "u1"))
            await store.set("acme", "u1", {"interests": {}})
            fetched = await store.get("acme", "u1")
            self.assertEqual(fetched, {"interests": {}})
            self.assertTrue(await store.delete("acme", "u1"))
            self.assertIsNone(await store.get("acme", "u1"))
            self.assertFalse(await store.delete("acme", "u1"))

        run(scenario())

    def test_tenant_isolation(self):
        store = ProfileStore()

        async def scenario():
            await store.set("acme", "u1", {"a": 1})
            self.assertIsNone(await store.get("globex", "u1"))

        run(scenario())

    def test_apply_updates_persists(self):
        store = ProfileStore()

        async def scenario():
            merged = await store.apply_updates("acme", "u1", [
                {"field": "interests.ai", "value": True, "confidence": 0.8},
            ])
            self.assertEqual(merged["interests"]["ai"]["value"], True)
            stored = await store.get("acme", "u1")
            self.assertEqual(stored["interests"]["ai"]["value"], True)

        run(scenario())

    def test_sync_client_profile(self):
        store = ProfileStore()

        async def scenario():
            await store.set("acme", "u1", {
                "preferences": {"role": {"value": "developer", "confidence": 0.9}},
            })
            merged = await store.sync_client_profile("acme", "u1", {
                "preferences": {"role": {"value": "student", "confidence": 0.4}},
                "interests": {"ai": {"value": True, "confidence": 0.7}},
            })
            self.assertEqual(merged["preferences"]["role"]["value"], "developer")
            self.assertEqual(merged["interests"]["ai"]["value"], True)

        run(scenario())


if __name__ == "__main__":
    unittest.main()
