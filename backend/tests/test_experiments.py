"""
Tests for holdout assignment and the metrics store.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import asyncio
import unittest

from experiments import ARM_CONTROL, ARM_NONE, ARM_PERSONALIZED, assign_arm
from metrics import MetricsStore


def run(coro):
    return asyncio.run(coro)


class TestAssignArm(unittest.TestCase):
    def test_sticky_assignment(self):
        arms = {assign_arm("user-42", 20, "exp-1") for _ in range(50)}
        self.assertEqual(len(arms), 1)

    def test_anonymous_excluded(self):
        self.assertEqual(assign_arm(None, 50), ARM_NONE)
        self.assertEqual(assign_arm("", 50), ARM_NONE)

    def test_zero_holdout_disables_experiment(self):
        self.assertEqual(assign_arm("user-42", 0), ARM_NONE)

    def test_full_holdout_everyone_control(self):
        for i in range(50):
            self.assertEqual(assign_arm(f"user-{i}", 100, "exp-1"), ARM_CONTROL)

    def test_distribution_roughly_matches_percent(self):
        n = 2000
        controls = sum(
            1 for i in range(n)
            if assign_arm(f"user-{i}", 10, "exp-1") == ARM_CONTROL
        )
        # 10% ± 2.5 percentage points over 2000 users
        self.assertGreater(controls, n * 0.075)
        self.assertLess(controls, n * 0.125)

    def test_salt_reshuffles_assignments(self):
        n = 500
        changed = sum(
            1 for i in range(n)
            if assign_arm(f"user-{i}", 50, "exp-1")
            != assign_arm(f"user-{i}", 50, "exp-2")
        )
        # With 50% holdout, ~half the users should switch arm on reshuffle
        self.assertGreater(changed, n * 0.3)

    def test_arms_are_valid(self):
        for i in range(100):
            self.assertIn(
                assign_arm(f"user-{i}", 30, "exp-1"),
                (ARM_CONTROL, ARM_PERSONALIZED),
            )


class TestMetricsStore(unittest.TestCase):
    def test_record_and_stats_with_uplift(self):
        store = MetricsStore()

        async def scenario():
            # personalized: 100 impressions, 10 clicks (CTR 0.10)
            await store.record("acme", "home", "personalized", "impression", 100)
            await store.record("acme", "home", "personalized", "click", 10)
            # control: 100 impressions, 5 clicks (CTR 0.05)
            await store.record("acme", "home", "control", "impression", 100)
            await store.record("acme", "home", "control", "click", 5)
            return await store.stats("acme", "home")

        stats = run(scenario())
        self.assertEqual(stats["arms"]["personalized"]["ctr"], 0.10)
        self.assertEqual(stats["arms"]["control"]["ctr"], 0.05)
        self.assertEqual(stats["uplift_percent"], 100.0)

    def test_no_uplift_without_control(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "personalized", "impression")
            await store.record("acme", "home", "personalized", "click")
            return await store.stats("acme", "home")

        stats = run(scenario())
        self.assertIsNone(stats["uplift_percent"])

    def test_ctr_none_without_impressions(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "personalized", "click")
            return await store.stats("acme", "home")

        stats = run(scenario())
        self.assertIsNone(stats["arms"]["personalized"]["ctr"])

    def test_tenant_and_zone_isolation(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "personalized", "impression")
            other_tenant = await store.stats("globex", "home")
            other_zone = await store.stats("acme", "footer")
            return other_tenant, other_zone

        other_tenant, other_zone = run(scenario())
        self.assertEqual(other_tenant["arms"], {})
        self.assertEqual(other_zone["arms"], {})

    def test_custom_event_types_counted(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "personalized", "conversion", 3)
            return await store.stats("acme", "home")

        stats = run(scenario())
        self.assertEqual(stats["arms"]["personalized"]["conversion"], 3)


if __name__ == "__main__":
    unittest.main()
