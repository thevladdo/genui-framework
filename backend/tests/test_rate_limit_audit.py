"""
Tests for the rate limiter and the audit logger.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import asyncio
import json
import os
import tempfile
import unittest

from utils.audit import AuditLogger, summarize_shown_components
from utils.rate_limit import RateLimiter


def run(coro):
    return asyncio.run(coro)


class TestRateLimiter(unittest.TestCase):
    def test_allows_within_limit(self):
        limiter = RateLimiter(limit=3, window_seconds=60)

        async def scenario():
            return [await limiter.allow("key") for _ in range(3)]

        self.assertEqual(run(scenario()), [True, True, True])

    def test_denies_beyond_limit(self):
        limiter = RateLimiter(limit=2, window_seconds=60)

        async def scenario():
            return [await limiter.allow("key") for _ in range(4)]

        self.assertEqual(run(scenario()), [True, True, False, False])

    def test_identities_are_independent(self):
        limiter = RateLimiter(limit=1, window_seconds=60)

        async def scenario():
            a1 = await limiter.allow("a")
            b1 = await limiter.allow("b")
            a2 = await limiter.allow("a")
            return a1, b1, a2

        self.assertEqual(run(scenario()), (True, True, False))

    def test_window_resets(self):
        limiter = RateLimiter(limit=1, window_seconds=0)

        async def scenario():
            first = await limiter.allow("key")
            await asyncio.sleep(0.01)
            second = await limiter.allow("key")
            return first, second

        self.assertEqual(run(scenario()), (True, True))

    def test_disabled_when_limit_zero(self):
        limiter = RateLimiter(limit=0)
        self.assertFalse(limiter.enabled)

        async def scenario():
            return all([await limiter.allow("key") for _ in range(100)])

        self.assertTrue(run(scenario()))


class TestAuditLogger(unittest.TestCase):
    def test_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            audit = AuditLogger(path=path)
            audit.log("zone_render", tenant="acme", user_id="u1",
                      zone_id="home", shown_links=["/a"])
            audit.log("profile_delete", tenant="acme", user_id="u2", existed=True)

            with open(path) as f:
                lines = [json.loads(line) for line in f]

            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["event"], "zone_render")
            self.assertEqual(lines[0]["tenant"], "acme")
            self.assertEqual(lines[0]["shown_links"], ["/a"])
            self.assertIn("ts", lines[0])
            self.assertEqual(lines[1]["event"], "profile_delete")

    def test_disabled_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            audit = AuditLogger(path=path, enabled=False)
            audit.log("x", tenant="t")
            self.assertFalse(os.path.exists(path))

    def test_never_raises_on_bad_path(self):
        audit = AuditLogger(path="/nonexistent-dir/audit.jsonl")
        # Falls back to the logger without raising
        audit.log("x", tenant="t")


class TestSummarizeShownComponents(unittest.TestCase):
    def test_summary_extracts_titles_and_links(self):
        components = [
            {"type": "bento", "data": {"cards": [
                {"title": "A", "link": "/a"},
                {"title": "B"},
            ]}},
            {"type": "buttons", "data": {"buttons": [
                {"label": "Go", "url": "/go"},
            ]}},
            {"type": "text", "data": {"content": "hi"}},
        ]
        summary = summarize_shown_components(components)
        self.assertEqual(summary["component_types"], ["bento", "buttons", "text"])
        self.assertEqual(summary["shown_titles"], ["A", "B", "Go"])
        self.assertEqual(summary["shown_links"], ["/a", "/go"])

    def test_empty_components(self):
        summary = summarize_shown_components([])
        self.assertEqual(summary["shown_links"], [])


if __name__ == "__main__":
    unittest.main()
