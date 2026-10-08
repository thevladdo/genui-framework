"""
An error has two readers: the client learns that it failed and how to find it again, the operator learns why.

(a) an exception in the render answers a generic 500 with a request id, and the exception text stays out of the response;
(b) an incoming X-Request-ID comes back out; without one, one is minted;
(c) the audit line of a render carries the request id of the response;
(d) in json format every log line is parseable JSON with the minimal fields, and the stack is in the log;
(e) the SSE error event carries no exception text;
(f) a model that fails on the render and on the chat leaves genui_llm_generations_total at "degraded", never "ok";
(g) with Qdrant unreachable the chat answers without documents and says so in its meta, never a 500.

The route tests need fastapi (backend venv).
"""

import asyncio
import io
import json
import logging
import os
import tempfile
import unittest
from unittest import mock

from memory_stores import use_memory_stores

try:
    from fastapi.testclient import TestClient

    import agents.response_agent as response_agent_module
    import agents.zone_agent as zone_agent_module
    import api.deps as deps
    import api.main as main
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    import metrics.ops as ops_module
    from agents.behave_agent import BehaveAgent
    from agents.orchestrator import AgentOrchestrator
    from agents.profile_agent import ProfileAgent
    from agents.response_agent import ResponseAgent
    from agents.zone_agent import ZoneAgent
    from config import settings
    from llm.base import LLMChatClient
    from metrics.ops import OpsMetrics
    from utils.audit import AuditLogger
    from utils.rate_limit import RateLimiter
    from utils.request_context import JsonFormatter, configure_logging
    from qdrant_client.http.exceptions import ResponseHandlingException
    from utils.zone_cache import ZoneRenderCache

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False
    LLMChatClient = object

SECRET = "host=secret.internal"
KEY = {"X-API-Key": "pk_test"}
ZONE = {"zone_id": "hero", "base_prompt": "Show content"}
ZONE_JSON = json.dumps({"components": [{"type": "text", "data": {"content": "hi"}}], "confidence": 0.9})
CHAT_JSON = json.dumps({"text_response": "From what I know, yes.", "components": [], "sources": [],
                        "confidence": 0.8, "suggested_actions": []})


def setUpModule():
    use_memory_stores()


class _LLM(LLMChatClient):
    """Answers with a fixed payload, or raises when payload is None."""

    def __init__(self, payload=None, search_first=False):
        self.payload = payload
        self.search_first = search_first
        self.tool_results = []

    def _answer(self):
        if self.payload is None:
            raise RuntimeError(f"provider timed out ({SECRET})")
        return self.payload

    async def complete_json(self, system, user, json_schema=None):
        return self._answer()

    async def complete_json_with_tools(self, system, user, tools, tool_handler, max_tool_rounds=3):
        if self.search_first:
            self.tool_results.append(await tool_handler("search_documents", {"query": "q"}))
        return self._answer()

    async def stream_json(self, system, user):
        yield self._answer()


class _NoDocuments:
    async def search_async(self, **kwargs):
        return []


class _RaisingZoneAgent:
    async def render_zone_async(self, request):
        raise RuntimeError(f"connection refused ({SECRET})")

    async def render_zone_stream_async(self, request):
        raise RuntimeError(f"connection refused ({SECRET})")
        yield


def _qdrant_down():
    raise ConnectionRefusedError(f"[Errno 61] Connection refused ({SECRET})")


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class ErrorsAndLogsTest(unittest.TestCase):
    def setUp(self):
        use_memory_stores()
        audit_dir = tempfile.TemporaryDirectory(prefix="genui-audit-")
        self.addCleanup(audit_dir.cleanup)
        self.audit_path = os.path.join(audit_dir.name, "audit.jsonl")
        saved = {
            name: getattr(settings, name)
            for name in ("client_api_keys", "admin_api_keys", "user_token_secrets", "genui_dev_open",
                         "redis_url", "llm_budget_per_hour", "zone_cache_enabled", "holdout_percent")
        }
        self.addCleanup(lambda: [setattr(settings, k, v) for k, v in saved.items()])
        settings.client_api_keys = "pk_test:acme"
        settings.admin_api_keys = "sk_test:acme"
        settings.user_token_secrets = ""
        settings.genui_dev_open = True
        settings.redis_url = None
        settings.llm_budget_per_hour = 0
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0
        for module, name, value in (
            (auth_deps, "_registry", None),
            (auth_deps, "_rate_limiter", RateLimiter(limit=1000, window_seconds=60)),
            (auth_deps, "_audit_logger", AuditLogger(path=self.audit_path, enabled=True)),
            (deps, "_llm_budget", None),
            (ops_module, "_ops", OpsMetrics()),
            (zone_router, "_zone_cache", ZoneRenderCache()),
        ):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        self.addCleanup(auth_deps._audit_logger.close)
        self.client = TestClient(main.app)

    def use_zone_agent(self, agent):
        patcher = mock.patch.object(zone_router, "get_zone_agent", lambda: agent)
        patcher.start()
        self.addCleanup(patcher.stop)

    def use_chat(self, llm, vector_store=None):
        orchestrator = AgentOrchestrator(
            response_agent=ResponseAgent(vector_store=vector_store, llm_client=llm),
            profile_agent=ProfileAgent(llm_client=llm),
            behave_agent=BehaveAgent(llm_client=llm),
        )
        patcher = mock.patch.object(main, "get_orchestrator", lambda: orchestrator)
        patcher.start()
        self.addCleanup(patcher.stop)

    def generations(self, op):
        self.client.get("/live")  # lets the fire-and-forget counters land
        text = asyncio.run(ops_module._ops.render_text())
        return [line for line in text.splitlines()
                if line.startswith("genui_llm_generations_total") and f'op="{op}"' in line]

    def audit_lines(self, event):
        with open(self.audit_path, encoding="utf-8") as f:
            return [r for r in map(json.loads, f) if r["event"] == event]

    def test_a_render_exception_is_a_generic_500_with_request_id(self):
        self.use_zone_agent(_RaisingZoneAgent())
        response = self.client.post("/api/v1/zone/render", headers=KEY, json=ZONE)

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret.internal", response.text)
        body = response.json()
        self.assertEqual(body["detail"], "Internal server error")
        self.assertEqual(body["request_id"], response.headers["X-Request-ID"])

    def test_b_request_id_is_echoed_or_minted(self):
        echoed = self.client.get("/live", headers={"X-Request-ID": "lb-7f3a"})
        self.assertEqual(echoed.headers["X-Request-ID"], "lb-7f3a")

        minted = self.client.get("/live")
        self.assertRegex(minted.headers["X-Request-ID"], r"^[0-9a-f]{32}$")
        self.assertNotEqual(minted.headers["X-Request-ID"], self.client.get("/live").headers["X-Request-ID"])

        forged = self.client.get("/live", headers={"X-Request-ID": "x\" injected=1"})
        self.assertRegex(forged.headers["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_c_render_audit_line_carries_the_request_id(self):
        self.use_zone_agent(ZoneAgent(vector_store=_NoDocuments(), llm_client=_LLM(ZONE_JSON)))
        response = self.client.post("/api/v1/zone/render", headers={**KEY, "X-Request-ID": "trace-c"}, json=ZONE)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.audit_lines("zone_render")[-1]["request_id"], "trace-c")

    def test_d_json_log_lines_parse_with_the_minimal_fields(self):
        root = logging.getLogger()
        saved = (root.handlers[:], root.level)
        self.addCleanup(lambda: (setattr(root, "handlers", saved[0]), root.setLevel(saved[1])))
        stream = io.StringIO()
        configure_logging("json", logging.INFO, stream=stream)
        self.use_zone_agent(_RaisingZoneAgent())

        response = self.client.post("/api/v1/zone/render", headers=KEY, json=ZONE)

        lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue({"ts", "level", "logger", "message", "request_id"} <= line.keys(), line)
        failure = [line for line in lines if line["level"] == "ERROR"][-1]
        self.assertEqual(failure["request_id"], response.headers["X-Request-ID"])
        self.assertEqual(failure["tenant"], "acme")
        self.assertIn("/api/v1/zone/render", failure["message"])
        self.assertIn("secret.internal", failure["exc"])

    def test_a_page_on_another_origin_reads_the_request_id_of_a_500(self):
        self.use_zone_agent(_RaisingZoneAgent())
        response = self.client.post("/api/v1/zone/render", headers={**KEY, "Origin": settings.cors_origins[0]}, json=ZONE)
        self.assertEqual(response.status_code, 500)
        exposed = [h.strip().lower() for h in response.headers.get("access-control-expose-headers", "").split(",")]
        self.assertIn("x-request-id", exposed)

    def test_d_audit_lines_reach_the_log_as_they_were_written(self):
        written = json.dumps({"event": "zone_render", "tenant": "acme"})
        record = logging.LogRecord("genui.audit", logging.INFO, __file__, 1, written, None, None)
        self.assertEqual(JsonFormatter().format(record), written)

    def test_e_sse_error_event_carries_no_exception_text(self):
        self.use_zone_agent(_RaisingZoneAgent())
        response = self.client.post("/api/v1/zone/render/stream", headers=KEY, json=ZONE)

        self.assertIn("event: error", response.text)
        self.assertNotIn("secret.internal", response.text)
        error = json.loads(response.text.split("event: error\ndata: ", 1)[1].split("\n", 1)[0])
        self.assertEqual(error["request_id"], response.headers["X-Request-ID"])
        self.assertEqual(error["detail"], "Internal server error")

    def test_e_batch_error_carries_no_exception_text(self):
        self.use_zone_agent(_RaisingZoneAgent())
        response = self.client.post("/api/v1/zone/batch-render", headers=KEY, json=[ZONE])

        self.assertNotIn("secret.internal", response.text)
        self.assertEqual(response.json()["results"][0]["request_id"], response.headers["X-Request-ID"])

    def test_f_failed_zone_model_counts_degraded_sync_and_stream(self):
        self.use_zone_agent(ZoneAgent(vector_store=_NoDocuments(), llm_client=_LLM(None)))
        sync = self.client.post("/api/v1/zone/render", headers=KEY, json=ZONE)
        stream = self.client.post("/api/v1/zone/render/stream", headers=KEY, json={**ZONE, "zone_id": "side"})

        self.assertEqual(sync.status_code, 200, sync.text)
        self.assertIn("event: complete", stream.text)
        self.assertEqual(self.generations("zone"),
                         ['genui_llm_generations_total{op="zone",outcome="degraded",tenant="acme"} 2'])

    def test_f_failed_chat_model_counts_degraded(self):
        self.use_chat(_LLM(None), vector_store=_NoDocuments())
        response = self.client.post("/api/v1/query", headers=KEY, json={"query": "Is it covered?"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], "I couldn't process your request right now.")
        self.assertEqual(self.generations("query"),
                         ['genui_llm_generations_total{op="query",outcome="degraded",tenant="acme"} 1'])

    def test_f_a_good_answer_still_counts_ok(self):
        self.use_chat(_LLM(CHAT_JSON), vector_store=_NoDocuments())
        self.client.post("/api/v1/query", headers=KEY, json={"query": "Is it covered?"})

        self.assertEqual(self.generations("query"),
                         ['genui_llm_generations_total{op="query",outcome="ok",tenant="acme"} 1'])

    def test_g_chat_without_qdrant_answers_and_says_so(self):
        llm = _LLM(CHAT_JSON, search_first=True)
        self.use_chat(llm)
        with mock.patch.object(response_agent_module, "get_vector_store", _qdrant_down):
            response = self.client.post("/api/v1/query", headers=KEY, json={"query": "Is it covered?"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("secret.internal", response.text)
        body = response.json()
        self.assertEqual(body["text"], "From what I know, yes.")
        self.assertEqual(body["meta"]["retrieval"], "unavailable")
        self.assertEqual(llm.tool_results, ["The knowledge base is unavailable."])

    def test_g_search_preview_without_qdrant_is_a_503_that_says_why(self):
        class _Down:
            async def search_async(self, **kwargs):
                raise ResponseHandlingException(ConnectionRefusedError(SECRET))

        with mock.patch.object(main, "get_vector_store", lambda: _Down()):
            response = self.client.post("/api/v1/documents/search", headers={"X-API-Key": "sk_test"}, json={"query": "price"})

        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("Retry-After", response.headers)
        self.assertNotIn("secret.internal", response.text)
        self.assertIn("knowledge base", response.json()["detail"])
        self.assertEqual(response.json()["request_id"], response.headers["X-Request-ID"])

    def test_g_document_list_without_qdrant_is_a_503_that_says_why(self):
        with mock.patch.object(main, "get_vector_store", lambda: _store_on(_DeadQdrant())):
            response = self.client.get("/api/v1/documents", headers={"X-API-Key": "sk_test"})

        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("Retry-After", response.headers)
        self.assertNotIn("secret.internal", response.text)

    def test_g_chat_with_qdrant_says_retrieval_ok(self):
        self.use_chat(_LLM(CHAT_JSON), vector_store=_NoDocuments())
        response = self.client.post("/api/v1/query", headers=KEY, json={"query": "Is it covered?"})
        self.assertEqual(response.json()["meta"]["retrieval"], "ok")

    def test_g_zone_without_qdrant_renders_without_documents(self):
        self.use_zone_agent(ZoneAgent(llm_client=_LLM(ZONE_JSON)))
        with mock.patch.object(zone_agent_module, "get_vector_store", _qdrant_down):
            response = self.client.post("/api/v1/zone/render", headers=KEY, json=ZONE)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.generations("zone"),
                         ['genui_llm_generations_total{op="zone",outcome="ok",tenant="acme"} 1'])



class _DeadQdrant:
    """Every call fails the way the client fails when Qdrant does not answer."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ResponseHandlingException(ConnectionRefusedError(SECRET))
        return fail


def _store_on(client):
    from rag.vector_store import QdrantVectorStore
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.collection_name = "genui_documents"
    store.hybrid = False
    store.has_lexical = False
    store.client = client
    return store


@unittest.skipUnless(HAVE_APP_DEPS, "requires qdrant-client and fastapi (backend venv)")
class KnowledgeBaseFailuresTest(unittest.TestCase):
    """An unreachable Qdrant is never reported as an empty knowledge base."""

    def test_reads_raise_instead_of_answering_empty(self):
        store = _store_on(_DeadQdrant())
        for name, args in [
            ("list_documents", ("acme",)),
            ("indexed_state", ("doc", "acme")),
            ("chunk_counts", ("acme",)),
            ("plain_points", ("acme",)),
            ("recount_tokens", ("acme",)),
            ("get_collection_stats", ("acme",)),
            ("delete_by_source", ("doc", "acme")),
        ]:
            with self.subTest(name), self.assertRaises(ResponseHandlingException):
                getattr(store, name)(*args)

    def test_a_failed_recount_does_not_store_zero(self):
        class _Counter:
            stored = []

            async def get(self, tenant):
                return None

            async def set(self, tenant, value):
                self.stored.append(value)

        counter = _Counter()
        with mock.patch.object(main, "get_corpus_size", lambda: counter), self.assertRaises(ResponseHandlingException):
            asyncio.run(main._corpus_tokens(_store_on(_DeadQdrant()), "acme"))
        self.assertEqual(counter.stored, [])

    def test_a_backfill_stopped_by_an_error_says_so(self):
        import rag.ingest_status as ingest_status

        class _Store:
            def plain_points(self, tenant, max_chunks):
                return [{"id": 1, "chunk_id": "c_0", "source_document": "doc", "content": "text"}]

            def chunk_counts(self, tenant):
                return {"chunks_total": 1, "chunks_contextualized": 0, "chunks_plain": 1}

        async def broken(*args, **kwargs):
            raise ResponseHandlingException(ConnectionRefusedError(SECRET))

        settings.admin_api_keys = "sk_test:acme"
        self.addCleanup(setattr, settings, "admin_api_keys", settings.admin_api_keys)
        with mock.patch.object(main, "get_vector_store", lambda: _Store()), mock.patch.object(main, "_backfill_documents", broken):
            response = TestClient(main.app).post(
                "/api/v1/documents/backfill", headers={"X-API-Key": "sk_test"}, json={"ingest_id": "run-1"}
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(asyncio.run(ingest_status.read("run-1", "acme"))["phase"], "failed")

    def test_any_route_answers_503_when_qdrant_does_not(self):
        settings.admin_api_keys = "sk_test:acme"
        self.addCleanup(setattr, settings, "admin_api_keys", settings.admin_api_keys)
        with mock.patch.object(main, "get_vector_store", lambda: _store_on(_DeadQdrant())):
            client = TestClient(main.app)
            responses = [
                client.delete("/api/v1/documents/doc", headers={"X-API-Key": "sk_test"}),
                client.get("/api/v1/documents/stats", headers={"X-API-Key": "sk_test"}),
            ]
        for response in responses:
            self.assertEqual(response.status_code, 503, response.text)
            self.assertIn("Retry-After", response.headers)
            self.assertNotIn("secret.internal", response.text)
            self.assertEqual(response.json()["request_id"], response.headers["X-Request-ID"])


if __name__ == "__main__":
    unittest.main()
