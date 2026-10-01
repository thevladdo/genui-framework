"""
The ingestion controls do what they say.

- USE_SEMANTIC_CHUNKING=false cuts at sentences and embeds nothing.
- A dry run embeds nothing, and states what the real cut will embed.
- A stopped run stays stopped: a call that carries the same id on does no
  work and says "cancelled".
- Extraction runs off the event loop, and an oversized upload is refused
  while it is being read, not after.

Runnable with `python -m unittest discover -s tests` from backend/ (venv).
"""

import asyncio
import random
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from memory_stores import use_memory_stores

try:
    from fastapi import HTTPException

    from api import main
    from rag import chunker as chunker_module
    from rag import ingest_status
    from rag.chunker import create_chunker

    HAVE_APP = True
except Exception:
    HAVE_APP = False


def setUpModule():
    """Runs and stops recorded here stay in memory, off the Redis of whoever runs the suite."""
    use_memory_stores()
    try:
        from rag import ingest_status
        from utils.tenant_json_store import TenantJsonStore
    except Exception:
        return
    ingest_status._STORE = TenantJsonStore(key_prefix="genui:ingest:")


def tearDownModule():
    try:
        from rag import ingest_status
    except Exception:
        return
    ingest_status._STORE = None


def run(coro):
    return asyncio.run(coro)


class _CountingEmbedder:
    model = "fake"

    def __init__(self):
        self.texts = 0

    def embed(self, texts):
        self.texts += len(texts)
        return [[random.random() for _ in range(8)] for _ in texts]


def _document(sentences=120):
    rng = random.Random(7)
    words = "revenue churn pricing latency cluster invoice policy tenant quota".split()
    return " ".join(
        " ".join(rng.choice(words) for _ in range(12)).capitalize() + "."
        for _ in range(sentences)
    )


AUTH = SimpleNamespace(tenant="acme", is_admin=True, key_fingerprint="k")


@unittest.skipUnless(HAVE_APP, "app deps not installed (runs in the venv)")
class ChunkingKnobTest(unittest.TestCase):
    def test_semantic_off_cuts_at_sentences_without_embedding(self):
        embedder = _CountingEmbedder()
        with mock.patch.object(chunker_module, "create_embedding_client", lambda: embedder), \
             mock.patch.object(chunker_module.settings, "use_semantic_chunking", False):
            chunks = create_chunker().chunk_text(_document(), {}, "doc")

        self.assertGreater(len(chunks), 0)
        self.assertEqual(embedder.texts, 0)

    def test_semantic_on_still_embeds(self):
        embedder = _CountingEmbedder()
        with mock.patch.object(chunker_module, "create_embedding_client", lambda: embedder), \
             mock.patch.object(chunker_module.settings, "use_semantic_chunking", True):
            create_chunker().chunk_text(_document(), {}, "doc")

        self.assertGreater(embedder.texts, 0)


@unittest.skipUnless(HAVE_APP, "app deps not installed (runs in the venv)")
class DryRunCostTest(unittest.TestCase):
    def _dry_run(self, text, semantic):
        embedder = _CountingEmbedder()

        class _Store:
            def indexed_state(self, source, tenant):
                return {}

        class _Counter:
            async def get(self, tenant):
                return 0

        with mock.patch.object(chunker_module, "create_embedding_client", lambda: embedder), \
             mock.patch.object(chunker_module.settings, "use_semantic_chunking", semantic), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter()), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"):
            report = run(main._chunk_and_index(text, {}, "doc", "acme", dry_run=True))
        return report, embedder

    def test_the_estimate_embeds_nothing_and_names_the_real_cost(self):
        text = _document()
        report, embedder = self._dry_run(text, semantic=True)

        self.assertEqual(report["status"], "estimated")
        self.assertEqual(embedder.texts, 0, "the estimate itself spends nothing")
        self.assertEqual(report["chunking"], "semantic")
        self.assertTrue(report["chunks_approximate"])

        real = _CountingEmbedder()
        with mock.patch.object(chunker_module.settings, "use_semantic_chunking", True):
            create_chunker(embed_model=real).chunk_text(text, {}, "doc")
        self.assertEqual(report["cutting_embeddings"], real.texts)

    def test_with_sentence_chunking_the_estimate_is_exact_and_free(self):
        report, embedder = self._dry_run(_document(), semantic=False)

        self.assertEqual(embedder.texts, 0)
        self.assertEqual(report["chunking"], "sentence")
        self.assertEqual(report["cutting_embeddings"], 0)
        self.assertFalse(report["chunks_approximate"])


@unittest.skipUnless(HAVE_APP, "app deps not installed (runs in the venv)")
class StopIsTerminalTest(unittest.TestCase):
    """A stop is the operator's. Nothing that carries the run on may undo it."""

    def _backfill(self, state, ingest_id, cancel_after=None):
        situated = []

        class _Store:
            def plain_points(self, tenant, max_points):
                return [dict(p) for p in state.values() if not p["done"]][:max_points]

            def chunk_counts(self, tenant):
                plain = sum(1 for p in state.values() if not p["done"])
                return {"chunks_total": len(state),
                        "chunks_contextualized": len(state) - plain,
                        "chunks_plain": plain}

            def recontextualize(self, chunks, point_ids):
                for point_id in point_ids:
                    state[point_id]["done"] = True
                return len(point_ids)

        async def _contextualize(document, chunks, should_continue=None):
            for chunk in chunks:
                chunk.context = "situated"
                situated.append(chunk.chunk_id)
            if cancel_after is not None and len(situated) >= cancel_after:
                await ingest_status.cancel(ingest_id, "acme")
            return len(chunks)

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        request = main.BackfillRequest(ingest_id=ingest_id, max_chunks=500)
        with mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextualize", _contextualize), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            report = run(main.backfill_context(request, AUTH))
        return report, situated

    def _state(self, n):
        return {
            i: {"id": i, "chunk_id": f"doc_{i}", "source_document": "doc",
                "content": f"passage {i}", "done": False}
            for i in range(n)
        }

    def test_a_continuation_with_the_same_id_after_a_stop_does_nothing(self):
        state = self._state(200)

        first, situated = self._backfill(state, "bf-stop", cancel_after=main._INGEST_BATCH)
        self.assertEqual(first["status"], "cancelled")
        self.assertEqual(first["chunks_contextualized"], main._INGEST_BATCH)
        self.assertEqual(len(situated), main._INGEST_BATCH)

        second, situated_again = self._backfill(state, "bf-stop")
        self.assertEqual(second["status"], "cancelled")
        self.assertEqual(second["chunks_contextualized"], 0)
        self.assertEqual(situated_again, [], "no chunk is worked after a stop")
        self.assertEqual(sum(p["done"] for p in state.values()), main._INGEST_BATCH)

    def test_a_new_id_is_the_explicit_way_to_carry_on(self):
        state = self._state(120)
        self._backfill(state, "bf-a", cancel_after=main._INGEST_BATCH)

        report, situated = self._backfill(state, "bf-b")
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(situated), 120 - main._INGEST_BATCH)

    def test_an_upload_stopped_between_its_two_phases_stays_stopped(self):
        """The upload registers its id twice; the second time must not
        reopen a stop that arrived in between."""
        indexed = []

        class _Store:
            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, batch, tenant):
                indexed.extend(batch)
                return len(batch)

        class _Counter:
            async def get(self, tenant):
                return 0

        chunk = SimpleNamespace(content="text", chunk_id="doc_0", source_document="doc",
                                metadata={}, context=None)

        async def scenario():
            original = main._corpus_tokens

            async def _stop_meanwhile(store, tenant):
                await ingest_status.cancel("up-stop", "acme")
                return await original(store, tenant)

            with mock.patch.object(main, "_corpus_tokens", _stop_meanwhile):
                return await main._chunk_and_index(
                    "text", {}, "doc", "acme", ingest_id="up-stop"
                )

        with mock.patch.object(main, "_chunk_document", lambda *a: [chunk]), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter()):
            report = run(scenario())

        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(indexed, [])


@unittest.skipUnless(HAVE_APP, "app deps not installed (runs in the venv)")
class SharedStopFlagTest(unittest.TestCase):
    def test_the_stop_flag_is_kept_where_every_worker_reads_it(self):
        """The run and the request that stops it are served by different
        workers: the flag has to live on the deployment's Redis."""
        from config import settings
        from utils.redis_conn import shared_redis

        url = "redis://workers-share-this:6379/0"
        with mock.patch.object(settings, "redis_url", url), \
             mock.patch.object(ingest_status, "_STORE", None):
            store = ingest_status._store()

        self.assertIs(store._conn, shared_redis(url))


class _UploadFile:
    """What the route reads from: an async `read(n)` over some bytes."""

    def __init__(self, data, filename="doc.pdf"):
        self.data = data
        self.filename = filename
        self.served = 0

    async def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.data) - self.served
        block = self.data[self.served:self.served + size]
        self.served += len(block)
        return block


@unittest.skipUnless(HAVE_APP, "app deps not installed (runs in the venv)")
class UploadReadTest(unittest.TestCase):
    def _upload(self, file):
        return main.upload_document_file(
            file=file, title=None, url=None, dry_run=True, ingest_id="", auth=AUTH,
        )

    def test_extraction_does_not_block_the_event_loop(self):
        blocking = 0.3

        def _slow_extract(filename, content, backend=None):
            time.sleep(blocking)
            return "extracted text"

        async def _index(*args, **kwargs):
            return {"status": "estimated"}

        async def scenario():
            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.01)
                    ticks += 1

            spinner = asyncio.create_task(ticker())
            try:
                await self._upload(_UploadFile(b"%PDF-1.4 fake"))
            finally:
                spinner.cancel()
            return ticks

        with mock.patch("rag.extractors.extract_text", _slow_extract), \
             mock.patch.object(main, "_chunk_and_index", _index):
            ticks = run(scenario())

        self.assertGreater(ticks, 5)

    def test_an_oversized_upload_is_refused_before_it_is_read_whole(self):
        limit = 64 * 1024
        file = _UploadFile(b"x" * (limit * 40))

        with mock.patch("rag.extractors.max_file_size_bytes", lambda: limit), \
             mock.patch.object(main, "_READ_BLOCK", 16 * 1024):
            with self.assertRaises(HTTPException) as raised:
                run(self._upload(file))

        self.assertEqual(raised.exception.status_code, 413)
        self.assertLessEqual(file.served, limit + 16 * 1024)

    def test_a_file_at_the_limit_goes_through(self):
        limit = 64 * 1024
        seen = {}

        def _extract(filename, content, backend=None):
            seen["bytes"] = len(content)
            return "text"

        async def _index(*args, **kwargs):
            return {"status": "estimated"}

        with mock.patch("rag.extractors.max_file_size_bytes", lambda: limit), \
             mock.patch("rag.extractors.extract_text", _extract), \
             mock.patch.object(main, "_chunk_and_index", _index):
            run(self._upload(_UploadFile(b"x" * limit)))

        self.assertEqual(seen["bytes"], limit)

    def test_the_limit_is_max_upload_mb(self):
        from config import settings
        from rag import extractors

        with mock.patch.object(settings, "max_upload_mb", 3):
            self.assertEqual(extractors.max_file_size_bytes(), 3 * 1024 * 1024)

            file = _UploadFile(b"x" * (3 * 1024 * 1024 + 1))
            with self.assertRaises(HTTPException) as raised:
                run(self._upload(file))

        self.assertEqual(raised.exception.status_code, 413)
        self.assertIn("3 MB", raised.exception.detail)
        self.assertIn("MAX_UPLOAD_MB", raised.exception.detail)

    def test_the_console_is_told_the_limit_before_it_uploads(self):
        from config import settings

        class _Store:
            def list_documents(self, tenant):
                return []

            def chunk_counts(self, tenant):
                return {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}

        async def _tokens(store, tenant):
            return 0

        with mock.patch.object(settings, "max_upload_mb", 7), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "_corpus_tokens", _tokens):
            listing = run(main.list_documents(auth=AUTH))

        self.assertEqual(listing["corpus"]["max_upload_bytes"], 7 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
