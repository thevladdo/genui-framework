"""
Tests for observability & audit (roadmap WP-08): what a regulated
customer must observe (health, "who saw what") has to be queryable and
reliable, not a side effect on a local disk.

Covered here:
- OpsMetrics: Prometheus text rendering, label escaping, counter/summary
  typing, cross-worker Redis backend with in-memory flap fallback.
- provider_configured: the /health "llm" signal (config-level, no I/O).
- AuditLogger: stdlib rotation for the file sink, logger sink fallback,
  no handler stacking across instances.
- Endpoints (venv only): /health exposes statuses but no collection
  internals, /live, /ready contract, /metrics behind an admin key,
  render/generation counters at their choke points.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The endpoint tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import json
import os
import tempfile
import types
import unittest
from unittest import mock

from llm.factory import ProviderConfig, provider_configured
from metrics.ops import OpsMetrics, sample_key
from utils.audit import AuditLogger

try:  # app-level deps: available in the backend venv, not in the shell python
    from fastapi.testclient import TestClient

    import api.main as main
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    import metrics.ops as ops_module
    from auth.keys import AuthContext, KeyRegistry
    from config import settings
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP = True
except Exception:
    HAVE_APP = False


class TestSampleKey(unittest.TestCase):
    def test_no_labels_is_bare_name(self):
        self.assertEqual(sample_key("genui_up"), "genui_up")

    def test_labels_sorted_for_stable_identity(self):
        self.assertEqual(
            sample_key("m", {"b": "2", "a": "1"}),
            'm{a="1",b="2"}',
        )

    def test_label_values_escaped(self):
        key = sample_key("m", {"l": 'a"b\\c\nd'})
        self.assertEqual(key, 'm{l="a\\"b\\\\c\\nd"}')


class TestOpsMetricsMemory(unittest.TestCase):
    """No Redis URL: pure in-memory counters (single-process dev)."""

    def test_counter_and_text_format(self):
        ops = OpsMetrics()

        async def scenario():
            await ops.inc("genui_zone_renders_total", {"tenant": "acme", "cache": "miss"})
            await ops.inc("genui_zone_renders_total", {"tenant": "acme", "cache": "miss"})
            return await ops.render_text()

        text = asyncio.run(scenario())
        self.assertIn("# TYPE genui_zone_renders_total counter", text)
        self.assertIn('genui_zone_renders_total{cache="miss",tenant="acme"} 2', text)

    def test_summary_pair_typed_once(self):
        ops = OpsMetrics()

        async def scenario():
            await ops.inc("genui_llm_generation_seconds_sum", {"op": "zone"}, 1.5)
            await ops.inc("genui_llm_generation_seconds_count", {"op": "zone"})
            return await ops.render_text()

        text = asyncio.run(scenario())
        self.assertIn("# TYPE genui_llm_generation_seconds summary", text)
        self.assertIn('genui_llm_generation_seconds_sum{op="zone"} 1.5', text)
        self.assertIn('genui_llm_generation_seconds_count{op="zone"} 1', text)
        # The pair shares ONE TYPE line, on the base name
        self.assertNotIn("TYPE genui_llm_generation_seconds_sum", text)

    def test_redis_gauge_reports_disabled_as_zero(self):
        text = asyncio.run(OpsMetrics().render_text())
        self.assertIn("genui_redis_connected 0", text)

    def test_extra_gauges_rendered(self):
        text = asyncio.run(OpsMetrics().render_text({"genui_llm_configured": 1.0}))
        self.assertIn("# TYPE genui_llm_configured gauge", text)
        self.assertIn("genui_llm_configured 1", text)

    def test_observe_without_running_loop_counts_in_memory(self):
        ops = OpsMetrics()
        ops.observe("genui_http_requests_total", {"path": "/live"})
        text = asyncio.run(ops.render_text())
        self.assertIn('genui_http_requests_total{path="/live"} 1', text)

    def test_observe_inside_loop_is_fire_and_forget(self):
        ops = OpsMetrics()

        async def scenario():
            ops.observe("m_total", value=3)
            await asyncio.gather(*ops.pending_tasks())
            return await ops.render_text()

        self.assertIn("m_total 3", asyncio.run(scenario()))


class _FakeRedisHash:
    """Duck-typed async Redis exposing just the hash ops OpsMetrics uses."""

    def __init__(self):
        self.hashes = {}

    async def hincrbyfloat(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0.0) + float(value)
        return bucket[field]

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


class _FakeConn:
    """Duck-typed utils.redis_conn.ReconnectingRedis."""

    def __init__(self, client):
        self.client = client
        self.failures = 0

    @property
    def status(self):
        return "connected" if self.client is not None else "reconnecting"

    async def get(self):
        return self.client

    async def mark_failure(self, error):
        self.failures += 1
        self.client = None


class TestOpsMetricsRedis(unittest.TestCase):
    def test_counts_go_to_redis_and_merge_with_flap_window(self):
        ops = OpsMetrics()
        redis = _FakeRedisHash()
        ops._conn = _FakeConn(redis)

        async def scenario():
            await ops.inc("m_total", value=2)  # lands in redis
            ops._conn.client = None  # Redis blip
            await ops.inc("m_total", value=1)  # lands in memory
            ops._conn.client = redis  # recovered
            return await ops.render_text()

        text = asyncio.run(scenario())
        # Scrape merges the shared backend with the flap-window memory counts
        self.assertIn("m_total 3", text)
        self.assertIn("genui_redis_connected 1", text)

    def test_redis_error_falls_back_to_memory(self):
        class Exploding:
            async def hincrbyfloat(self, *a):
                raise ConnectionError("boom")

            async def hgetall(self, key):
                raise ConnectionError("boom")

        ops = OpsMetrics()
        ops._conn = _FakeConn(Exploding())

        async def scenario():
            await ops.inc("m_total")
            return await ops.render_text()

        text = asyncio.run(scenario())
        self.assertIn("m_total 1", text)
        self.assertGreaterEqual(ops._conn.failures, 1)


class TestProviderConfigured(unittest.TestCase):
    """The /health 'llm' signal: config presence, no network, no spend."""

    def test_key_present_is_configured(self):
        self.assertTrue(provider_configured(ProviderConfig("openai", "sk-x", None)))
        self.assertTrue(provider_configured(ProviderConfig("anthropic", "sk-a", None)))

    def test_keyless_openai_compatible_endpoint_is_configured(self):
        # Local vLLM/Ollama endpoints legitimately run without a key
        self.assertTrue(provider_configured(ProviderConfig("openai", None, "http://vllm:8000/v1")))

    def test_missing_key_is_unconfigured(self):
        self.assertFalse(provider_configured(ProviderConfig("openai", None, None)))
        self.assertFalse(provider_configured(ProviderConfig("anthropic", None, None)))
        # Gemini always has a base_url (Google's); without a key it is NOT usable
        self.assertFalse(
            provider_configured(ProviderConfig("gemini", None, "https://generativelanguage.googleapis.com/v1beta/openai/"))
        )


class TestAuditRotation(unittest.TestCase):
    def _event(self, audit, i=0):
        audit.log("zone_render", tenant="acme", user_id=f"user-{i}", zone_id="z1", padding="x" * 80)

    def test_file_sink_rotates_at_max_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            audit = AuditLogger(path=path, max_bytes=300, backup_count=2)
            for i in range(10):
                self._event(audit, i)

            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.exists(path + ".1"), "no rotated file: audit grows unbounded")
            with open(path, encoding="utf-8") as f:
                for line in f:
                    record = json.loads(line)  # rotation must not corrupt lines
                    self.assertEqual(record["tenant"], "acme")
                    self.assertIn("ts", record)

    def test_max_bytes_zero_never_rotates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            audit = AuditLogger(path=path, max_bytes=0, backup_count=2)
            for i in range(10):
                self._event(audit, i)
            self.assertFalse(os.path.exists(path + ".1"))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 10)

    def test_two_instances_do_not_stack_handlers(self):
        """getLogger-style handler stacking would double-write every line."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            first = AuditLogger(path=path)
            second = AuditLogger(path=path)
            self._event(first)
            self._event(second)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 2)

    def test_no_path_emits_on_audit_logger(self):
        audit = AuditLogger(path=None)
        with self.assertLogs("genui.audit", level="INFO") as captured:
            audit.log("query", tenant="acme", user_id="u1")
        record = json.loads(captured.output[0].split(":", 2)[2])
        self.assertEqual(record["event"], "query")
        self.assertEqual(record["tenant"], "acme")

    def test_unwritable_path_falls_back_to_logger(self):
        audit = AuditLogger(path="/nonexistent-dir/audit.jsonl")
        with self.assertLogs("genui.audit", level="INFO") as captured:
            audit.log("query", tenant="acme")
        self.assertIn('"event": "query"', captured.output[-1])

    def test_disabled_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            AuditLogger(path=path, enabled=False).log("query", tenant="acme")
            self.assertFalse(os.path.exists(path))


def _fake_result():
    return types.SimpleNamespace(
        components=[{"type": "text", "data": {"content": "hi"}}],
        pinned_content_included=[],
        personalization_applied=False,
        confidence=0.9,
        reasoning="",
        profile_factors_used=[],
        removed_urls=[],
        dropped_components=[],
        removed_numbers=[],
        policy_violations=[],
    )


@unittest.skipUnless(HAVE_APP, "requires fastapi (backend venv)")
class ObservabilityAppTest(unittest.TestCase):
    """Shared fixture: fresh ops singleton, in-memory stores, no real LLM."""

    def setUp(self):
        self._saved = (
            ops_module._ops,
            zone_router._zone_cache,
            zone_router._llm_budget,
            auth_deps._rate_limiter,
            auth_deps._registry,
            settings.redis_url,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.llm_budget_per_hour,
        )
        ops_module._ops = OpsMetrics()  # in-memory, isolated per test
        zone_router._zone_cache = ZoneRenderCache()
        zone_router._llm_budget = None
        auth_deps._rate_limiter = None
        auth_deps._registry = None
        settings.redis_url = None
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0
        settings.llm_budget_per_hour = 0

    def tearDown(self):
        (
            ops_module._ops,
            zone_router._zone_cache,
            zone_router._llm_budget,
            auth_deps._rate_limiter,
            auth_deps._registry,
            settings.redis_url,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.llm_budget_per_hour,
        ) = self._saved


class TestHealthEndpoints(ObservabilityAppTest):
    def test_health_exposes_no_collection_internals(self):
        body = TestClient(main.app).get("/health").json()
        self.assertNotIn("collection_stats", body)
        self.assertIn("llm", body)
        self.assertIn("redis", body)
        self.assertIn("qdrant_connected", body)

    def test_health_reports_llm_unconfigured(self):
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", None), \
             mock.patch.object(settings, "openai_base_url", None):
            body = TestClient(main.app).get("/health").json()
        self.assertEqual(body["llm"], "unconfigured")
        self.assertEqual(body["status"], "degraded")

    def test_live_is_always_alive(self):
        response = TestClient(main.app).get("/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "alive"})

    def test_ready_503_when_llm_unconfigured(self):
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", None), \
             mock.patch.object(settings, "openai_base_url", None):
            response = TestClient(main.app).get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["llm"], "unconfigured")

    def test_ready_200_when_llm_configured_even_if_degraded(self):
        """Degraded-but-serving must stay in the LB rotation: pulling every
        replica for a shared-dependency blip turns degradation into an outage."""
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", "sk-test"):
            response = TestClient(main.app).get("/ready")
        self.assertEqual(response.status_code, 200)


class TestMetricsEndpoint(ObservabilityAppTest):
    def _client(self):
        auth_deps._registry = KeyRegistry(
            client_keys=["pk_c:acme"], admin_keys=["sk_a:acme"]
        )
        return TestClient(main.app)

    def test_metrics_requires_admin_key(self):
        client = self._client()
        self.assertEqual(client.get("/metrics").status_code, 401)
        self.assertEqual(
            client.get("/metrics", headers={"X-API-Key": "pk_c"}).status_code, 403
        )

    def test_metrics_scrape_with_admin_key(self):
        client = self._client()
        client.get("/live")
        client.get("/metrics", headers={"X-API-Key": "sk_a"})  # flush tick
        response = client.get("/metrics", headers={"X-API-Key": "sk_a"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["content-type"])
        self.assertIn("genui_http_requests_total", response.text)
        self.assertIn('path="/live"', response.text)
        self.assertIn("genui_http_request_seconds_sum", response.text)
        self.assertIn("genui_llm_configured", response.text)

    def test_unmatched_paths_do_not_explode_cardinality(self):
        client = self._client()
        client.get("/no-such-page-1")
        client.get("/no-such-page-2")
        client.get("/metrics", headers={"X-API-Key": "sk_a"})  # flush tick
        text = client.get("/metrics", headers={"X-API-Key": "sk_a"}).text
        self.assertIn('path="unmatched"', text)
        self.assertNotIn("no-such-page", text)


class TestRenderCounters(ObservabilityAppTest):
    CLIENT = None

    @classmethod
    def setUpClass(cls):
        cls.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")

    def _request(self, zone_id="zone-1"):
        return zone_router.ZoneRenderRequest(zone_id=zone_id, base_prompt="Show content")

    def test_served_renders_counted_per_cache_status(self):
        async def fake_render(request, tenant, segment=None):
            return {
                "render_id": "r1",
                "components": [],
                "pinned_content_included": [],
                "personalization_applied": False,
                "meta": {},
                "rendered_at": "2026-07-15T00:00:00+00:00",
            }

        async def scenario():
            with mock.patch.object(zone_router, "_render_live", fake_render):
                await zone_router._handle_render(self._request(), self.CLIENT)
                await zone_router._handle_render(self._request(), self.CLIENT)
            await asyncio.gather(*ops_module._ops.pending_tasks())
            return await ops_module._ops.render_text()

        text = asyncio.run(scenario())
        self.assertIn('genui_zone_renders_total{cache="miss",tenant="acme"} 1', text)
        self.assertIn('genui_zone_renders_total{cache="fresh",tenant="acme"} 1', text)

    def test_llm_generation_counted_with_duration(self):
        agent = types.SimpleNamespace()

        async def render_zone_async(agent_request):
            return _fake_result()

        agent.render_zone_async = render_zone_async

        async def scenario():
            with mock.patch.object(zone_router, "get_zone_agent", lambda: agent):
                await zone_router._handle_render(self._request(), self.CLIENT)
            await asyncio.gather(*ops_module._ops.pending_tasks())
            return await ops_module._ops.render_text()

        text = asyncio.run(scenario())
        self.assertIn('genui_llm_generations_total{op="zone",outcome="ok",tenant="acme"} 1', text)
        self.assertIn('genui_llm_generation_seconds_count{op="zone",tenant="acme"} 1', text)

    def test_failed_generation_counted_as_error(self):
        agent = types.SimpleNamespace()

        async def render_zone_async(agent_request):
            raise RuntimeError("provider down")

        agent.render_zone_async = render_zone_async

        async def scenario():
            with mock.patch.object(zone_router, "get_zone_agent", lambda: agent):
                try:
                    await zone_router._handle_render(self._request(), self.CLIENT)
                except RuntimeError:
                    pass
            await asyncio.gather(*ops_module._ops.pending_tasks())
            return await ops_module._ops.render_text()

        text = asyncio.run(scenario())
        self.assertIn('genui_llm_generations_total{op="zone",outcome="error",tenant="acme"} 1', text)


if __name__ == "__main__":
    unittest.main()
