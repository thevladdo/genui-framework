"""
Qdrant must never block the worker that reports on it.

The search path was already asynchronous, so the subject is everything else: 
the health probe rebuilt a whole vector store (and its collection bring-up) 
on every call, from an `async def`, with the synchronous client. 
The two routes an orchestrator polls every few seconds were the routes doing 
the most blocking network work in the process, so a slow Qdrant stopped the 
event loop through the very probes that exist to notice it, and a degraded 
dependency turned into a totaloutage.

What is pinned here:

- a slow synchronous Qdrant call leaves the event loop free (other
  coroutines keep making progress while it runs);
- the store is built once per process, not once per request;
- a failed first construction is not remembered, so a Qdrant that boots
  late is not reported down forever;
- the connection is reused but the health answer is not: with Qdrant
  unreachable, /health still says so, and the health/ready contract is
  unchanged.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The store tests use the fake qdrant modules of test_embeddings (no SDK,
no network); the endpoint tests need fastapi and skip in the shell
interpreter.
"""

import asyncio
import time
import unittest
from unittest import mock

from tests.test_embeddings import (
    FakeQdrantServer,
    MockEmbedder,
    VectorStoreTestCase,
    fake_settings,
)

try:
    from fastapi.testclient import TestClient

    import api.main as main

    HAVE_APP = True
except Exception:
    HAVE_APP = False


class SharedVectorStoreTest(VectorStoreTestCase):
    """The costly, cacheable half: construction."""

    def test_store_is_built_once_per_process(self):
        module = self.load(self._server(), fake_settings())
        built = []

        def _counting_init(self, *args, **kwargs):
            built.append(1)

        with mock.patch.object(module.QdrantVectorStore, "__init__", _counting_init):
            first = module.get_vector_store()
            for _ in range(5):
                self.assertIs(module.get_vector_store(), first)

        self.assertEqual(len(built), 1)

    def test_failed_construction_is_not_remembered(self):
        """Qdrant down at boot must not pin the process to 'down' forever."""
        module = self.load(self._server(), fake_settings())
        attempts = []

        def _flaky_init(self, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("qdrant not up yet")

        with mock.patch.object(module.QdrantVectorStore, "__init__", _flaky_init):
            with self.assertRaises(ConnectionError):
                module.get_vector_store()
            self.assertIsNotNone(module.get_vector_store())

        self.assertEqual(len(attempts), 2)

    def test_clients_get_a_bounded_timeout(self):
        """A hung Qdrant costs a bounded wait, like the other infra handle."""
        server = self._server()
        module = self.load(server, fake_settings(qdrant_timeout_seconds=2))
        store = module.QdrantVectorStore(embedder=MockEmbedder(dim=768))
        self.assertEqual(store.client.timeout, 2)
        self.assertEqual(store.async_client.timeout, 2)

    def _server(self):
        return FakeQdrantServer()

    def load(self, server, settings_ns):
        module = super().load(server, settings_ns)
        module.get_vector_store.cache_clear()
        self.addCleanup(module.get_vector_store.cache_clear)
        return module


@unittest.skipUnless(HAVE_APP, "fastapi not installed (runs in the venv)")
class HealthOffEventLoopTest(unittest.TestCase):
    def test_slow_qdrant_does_not_block_the_event_loop(self):
        """
        The honest version of the claim: while the blocking Qdrant call
        runs, another coroutine must keep getting scheduled. If the call
        sits on the loop, the ticker cannot advance at all.
        """
        blocking = 0.3

        class _SlowStore:
            def get_collection_stats(self):
                time.sleep(blocking)  # a synchronous, hung dependency
                return {"points_count": 1}

        async def scenario():
            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.01)
                    ticks += 1

            spinner = asyncio.create_task(ticker())
            try:
                health = await main._dependency_health()
            finally:
                spinner.cancel()
            return health, ticks

        with mock.patch.object(main, "get_vector_store", lambda: _SlowStore()):
            health, ticks = asyncio.run(scenario())

        self.assertTrue(health.qdrant_connected)
        self.assertGreater(ticks, 5)

    def test_health_still_tells_the_truth_when_qdrant_is_unreachable(self):
        """A reused connection must never mask a dead Qdrant."""

        def _unreachable():
            raise ConnectionError("connection refused")

        with mock.patch.object(main, "get_vector_store", _unreachable):
            response = TestClient(main.app).get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["qdrant_connected"])
        self.assertEqual(body["status"], "degraded")

    def test_ready_contract_unchanged_when_qdrant_is_unreachable(self):
        """Qdrant down is degradation, not unreadiness: the replica serves."""
        from config import settings

        def _unreachable():
            raise ConnectionError("connection refused")

        with mock.patch.object(main, "get_vector_store", _unreachable), \
             mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", "sk-test"):
            response = TestClient(main.app).get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["qdrant_connected"])


@unittest.skipUnless(HAVE_APP, "fastapi not installed (runs in the venv)")
class DocumentRoutesOffEventLoopTest(unittest.TestCase):
    """
    The admin routes are lower frequency, not lower risk: one slow
    listing on the event loop stalls every render the worker is serving.
    """

    def test_blocking_document_routes_run_in_the_threadpool(self):
        import inspect

        for route in (
            main.upload_document,
            main.list_documents,
            main.delete_document,
            main.get_document_stats,
            main._process_document_background,
        ):
            with self.subTest(route=route.__name__):
                self.assertFalse(
                    inspect.iscoroutinefunction(route),
                    f"{route.__name__} calls Qdrant synchronously: declaring it "
                    f"async puts those round-trips on the event loop",
                )


if __name__ == "__main__":
    unittest.main()
