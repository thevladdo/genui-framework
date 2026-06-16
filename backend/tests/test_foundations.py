"""
Tests for point-7 foundations: statistical significance, LLM provider
resolution, and the tracing no-op helper.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import asyncio
import unittest

from llm.factory import GEMINI_OPENAI_BASE_URL, resolve_provider_config
from metrics import MetricsStore
from metrics.significance import two_proportion_significance
from utils.tracing import span


def run(coro):
    return asyncio.run(coro)


class TestTwoProportionSignificance(unittest.TestCase):
    def test_clearly_significant_difference(self):
        # 10% vs 5% CTR over 10k impressions each: unambiguous
        result = two_proportion_significance(10000, 1000, 10000, 500)
        self.assertTrue(result["significant_95"])
        self.assertLess(result["p_value"], 0.001)
        self.assertGreater(result["z_score"], 0)
        self.assertFalse(result["sample_warning"])

    def test_noise_not_significant(self):
        # 11 vs 9 clicks over 200 impressions: noise
        result = two_proportion_significance(200, 11, 200, 9)
        self.assertFalse(result["significant_95"])
        self.assertGreater(result["p_value"], 0.05)

    def test_small_sample_warning(self):
        result = two_proportion_significance(50, 10, 50, 2)
        self.assertTrue(result["sample_warning"])

    def test_negative_z_when_control_wins(self):
        result = two_proportion_significance(1000, 50, 1000, 100)
        self.assertLess(result["z_score"], 0)

    def test_uncomputable_cases(self):
        self.assertIsNone(two_proportion_significance(0, 0, 100, 5))
        self.assertIsNone(two_proportion_significance(100, 5, 0, 0))
        # Zero variance: no clicks anywhere
        self.assertIsNone(two_proportion_significance(100, 0, 100, 0))

    def test_clicks_capped_at_impressions(self):
        result = two_proportion_significance(10, 50, 10, 1)
        self.assertIsNotNone(result)

    def test_wired_into_stats(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "personalized", "impression", 10000)
            await store.record("acme", "home", "personalized", "click", 1000)
            await store.record("acme", "home", "control", "impression", 10000)
            await store.record("acme", "home", "control", "click", 500)
            return await store.stats("acme", "home")

        stats = run(scenario())
        self.assertIsNotNone(stats["significance"])
        self.assertTrue(stats["significance"]["significant_95"])

    def test_stats_significance_none_without_control(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "personalized", "impression", 100)
            return await store.stats("acme", "home")

        self.assertIsNone(run(scenario())["significance"])


class TestResolveProviderConfig(unittest.TestCase):
    def test_openai_default(self):
        config = resolve_provider_config("openai", openai_api_key="sk-1")
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.api_key, "sk-1")
        self.assertIsNone(config.base_url)

    def test_openai_custom_base_url(self):
        config = resolve_provider_config(
            "openai", openai_api_key="sk-1", openai_base_url="http://vllm:8000/v1"
        )
        self.assertEqual(config.base_url, "http://vllm:8000/v1")

    def test_anthropic(self):
        config = resolve_provider_config("anthropic", anthropic_api_key="sk-ant")
        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.api_key, "sk-ant")

    def test_gemini_uses_openai_compatible_endpoint(self):
        for name in ("gemini", "google", "GEMINI"):
            config = resolve_provider_config(name, google_api_key="g-key")
            self.assertEqual(config.provider, "gemini")
            self.assertEqual(config.api_key, "g-key")
            self.assertEqual(config.base_url, GEMINI_OPENAI_BASE_URL)

    def test_unknown_provider_falls_back_to_openai(self):
        config = resolve_provider_config("hal9000", openai_api_key="sk-1")
        self.assertEqual(config.provider, "openai")

    def test_empty_provider_defaults_to_openai(self):
        self.assertEqual(resolve_provider_config("").provider, "openai")
        self.assertEqual(resolve_provider_config(None).provider, "openai")


class TestTracingSpanNoOp(unittest.TestCase):
    def test_span_is_safe_without_configuration(self):
        # Must never raise, with or without opentelemetry installed
        with span("genui.test", zone_id="z1", skipped=None) as s:
            # Without a configured provider this is None or a no-op span
            self.assertTrue(s is None or hasattr(s, "set_attribute"))

    def test_span_nesting(self):
        with span("outer"):
            with span("inner", depth=2):
                pass


if __name__ == "__main__":
    unittest.main()
