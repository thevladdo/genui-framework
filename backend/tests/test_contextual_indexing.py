"""
Indexing a chunk with the lines that situate it in its document.
Four properties:

1. THE GENERATED TEXT NEVER REACHES THE GUARANTEE CORPUS. The whitelist and
   the numeric grounding build the corpus they judge from out of retrieved
   content. If the situating lines were stored as the chunk's content, a
   figure invented while writing them would be a figure authorised at render
   time. The point keeps the original chunk; only the vectors see the rest.
2. The spend goes through the per-tenant cap, and a document that does not
   fit is indexed without context rather than left half indexed.
3. A chunk whose call fails is indexed as it is.
4. Whether a chunk carries context is recorded next to it, and an upload
   that resumes does not buy again what it already paid for.
"""

import asyncio
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

try:
    from rag.chunker import SemanticChunk
    from rag.contextualizer import (
        contextual_indexing_enabled,
        contextualize,
        document_view,
    )
    from rag.vector_store import (
        LEXICAL_VECTOR,
        QdrantVectorStore,
        content_hash,
        indexable_text,
        lexical_vector,
        point_id_for,
    )
    HAVE_DEPS = True
except Exception:
    HAVE_DEPS = False


def setUpModule():
    """Runs and stops recorded here stay in memory, off the Redis of whoever runs the suite."""
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


def point_id(text, occurrence=0):
    """Where a chunk holding this text belongs, by the real derivation."""
    return point_id_for("acme", "doc", content_hash(text), occurrence)


def chunk(content, chunk_id="doc_0", context=None):
    return SemanticChunk(
        content=content,
        metadata={},
        chunk_id=chunk_id,
        source_document="doc",
        context=context,
    )


class _Embedder:
    model = "text-embedding-3-small"

    def __init__(self):
        self.embedded = []

    @property
    def dimension(self):
        return 3

    def dimension_if_known(self):
        return 3

    def embed(self, texts):
        self.embedded.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class _Client:
    def __init__(self):
        self.upserted = []

    def upsert(self, collection_name, points):
        self.upserted.extend(points)


def _store(embedder, lexical=False):
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.collection_name = "genui_documents"
    store.embed_model = embedder
    store.client = _Client()
    store._collection_dim = 3
    store.has_lexical = lexical
    store.hybrid = lexical
    return store


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class IndexedTextTest(unittest.TestCase):
    def test_context_is_indexed_and_never_stored_as_content(self):
        """
        The context invents a figure and a link on purpose. The URL
        whitelist and the numeric grounding build the corpus they judge
        from out of retrieved content, so a number made up while situating
        a chunk would be a number authorised at render time: the
        guarantees would be enforcing a claim the model made about itself.
        """
        embedder = _Embedder()
        store = _store(embedder)
        situated = chunk(
            "Operating margin rose to 11.4 percent.",
            context="From the Northwind review: margins near 99 percent, "
                    "see https://invented.example",
        )

        store.index_chunks([situated], tenant="acme")
        self.assertEqual(len(embedder.embedded), 1)
        self.assertIn("Northwind", embedder.embedded[0])
        self.assertIn("Operating margin rose", embedder.embedded[0])

        payload = store.client.upserted[0].payload
        self.assertEqual(payload["content"], "Operating margin rose to 11.4 percent.")
        self.assertNotIn("Northwind", payload["content"])
        self.assertNotIn("99", payload["content"])
        self.assertNotIn("invented.example", payload["content"])
        self.assertTrue(payload["contextualized"])

    def test_both_vectors_are_built_from_the_chunk_with_its_context(self):
        """
        Dense and lexical are built separately, so the context can reach
        one and miss the other. The half that misses it stops matching the
        words the situating lines add, and the search quietly gets worse on
        exactly the questions this feature exists to answer.
        """
        embedder = _Embedder()
        store = _store(embedder, lexical=True)
        situated = chunk(
            "Operating margin rose to 11.4 percent.",
            context="This is from the Northwind review for fiscal 2025.",
        )

        store.index_chunks([situated], tenant="acme")

        self.assertIn("Northwind", embedder.embedded[0])
        lexical = store.client.upserted[0].vector[LEXICAL_VECTOR]
        self.assertEqual(
            set(lexical.indices),
            set(lexical_vector(indexable_text(situated)).indices),
            "the lexical vector must see the context too",
        )
        self.assertNotEqual(
            set(lexical.indices),
            set(lexical_vector(situated.content).indices),
        )

    def test_a_chunk_without_context_is_indexed_exactly_as_before(self):
        embedder = _Embedder()
        store = _store(embedder)

        store.index_chunks([chunk("A passage on its own.")], tenant="acme")

        self.assertEqual(embedder.embedded, ["A passage on its own."])
        payload = store.client.upserted[0].payload
        self.assertEqual(payload["content"], "A passage on its own.")
        self.assertFalse(payload["contextualized"])


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class ContextualizeTest(unittest.TestCase):
    def _patch_client(self, client):
        patcher = mock.patch("rag.contextualizer.create_llm_client", lambda model: client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_failed_call_leaves_the_chunk_indexable_as_it_is(self):
        class _HalfBroken:
            prompt_cache = "prefix"

            async def complete_json_cached(self, system, cached_prefix, user):
                if "second" in user:
                    raise RuntimeError("provider said no")
                return '{"context": "situated"}'

        self._patch_client(_HalfBroken())
        chunks = [chunk("the first one", "doc_0"), chunk("the second one", "doc_1")]

        written = run(contextualize("the whole document", chunks))

        self.assertEqual(written, 1)
        self.assertEqual(chunks[0].context, "situated")
        self.assertIsNone(chunks[1].context)
        self.assertEqual(indexable_text(chunks[1]), "the second one")

    def test_unparseable_output_is_a_failure_not_a_context(self):
        class _Babbling:
            prompt_cache = "prefix"

            async def complete_json_cached(self, system, cached_prefix, user):
                return "not json at all"

        self._patch_client(_Babbling())
        chunks = [chunk("a passage")]

        self.assertEqual(run(contextualize("document", chunks)), 0)
        self.assertIsNone(chunks[0].context)

    def test_the_document_is_sent_as_one_repeated_prefix(self):
        """The declared cost of this assumes the document is paid for once
        per batch, which only holds if every call sends it identically."""
        seen = []

        class _Recording:
            prompt_cache = "explicit"

            async def complete_json_cached(inner, system, cached_prefix, user):
                seen.append(cached_prefix)
                return '{"context": "c"}'

        self._patch_client(_Recording())
        run(contextualize("the whole document", [chunk("a", "doc_0"), chunk("b", "doc_1")]))

        self.assertEqual(len(seen), 2)
        self.assertEqual(len(set(seen)), 1, "the cached prefix must not vary")
        self.assertIn("the whole document", seen[0])


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class LargeDocumentTest(unittest.TestCase):
    """
    A document larger than the model's context used to be sent whole with
    every call: every one refused for exceeding the context, all of them
    still spending the rate limit, a thousand times over.
    """

    def test_a_document_over_the_budget_travels_as_a_view_of_itself(self):
        document = "HEAD: Northwind fiscal 2025. " + ("filler. " * 200_000)
        situated = chunk("a passage", context=None)
        situated.start_char = len(document) // 2

        view = document_view(document, situated)

        self.assertLess(len(view), len(document) / 10)
        self.assertIn("HEAD: Northwind fiscal 2025.", view,
                      "the opening carries the subject and the period")

    def test_a_document_within_the_budget_travels_whole(self):
        """The chunk is text of the document, so a view that started
        windowing everything would show up here as a document cut apart."""
        document = "A short document about Northwind. A passage about margins."
        self.assertEqual(
            document_view(document, chunk("A passage about margins.")), document
        )

    def test_a_batch_that_keeps_failing_the_same_way_stops(self):
        """
        A refusal is the model saying no, not a blip. Firing the other
        thousand chunks at it buys nothing and spends the rate limit.
        """
        attempts = []

        class _AlwaysRefuses:
            prompt_cache = "prefix"

            async def complete_json_cached(self, system, cached_prefix, user):
                attempts.append(user)
                raise RuntimeError("400 context_length_exceeded")

        with mock.patch("rag.contextualizer.create_llm_client",
                        lambda model: _AlwaysRefuses()):
            chunks = [chunk(f"passage {i}", f"doc_{i}") for i in range(200)]
            written = asyncio.run(contextualize("document", chunks))

        self.assertEqual(written, 0)
        self.assertLess(len(attempts), 20,
                        "the batch must stop, not grind through every chunk")
        self.assertTrue(all(c.context is None for c in chunks))


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class TenantSwitchTest(unittest.TestCase):
    def _settings(self, tenants="", threshold=200_000):
        return mock.patch(
            "rag.contextualizer.settings",
            SimpleNamespace(
                contextual_indexing_tenants=tenants,
                contextual_indexing_threshold_tokens=threshold,
                context_model="gpt-4o-mini",
            ),
        )

    def test_off_by_default_on_a_small_corpus(self):
        with self._settings():
            self.assertFalse(contextual_indexing_enabled("acme"))
            self.assertFalse(contextual_indexing_enabled("acme", corpus_tokens=199_999))

    def test_on_only_for_the_named_tenants(self):
        with self._settings(tenants="acme, globex"):
            self.assertTrue(contextual_indexing_enabled("acme"))
            self.assertTrue(contextual_indexing_enabled("globex"))
            self.assertFalse(contextual_indexing_enabled("initech"))
            self.assertFalse(contextual_indexing_enabled(None))

    def test_above_the_threshold_it_applies_without_anyone_switching_it_on(self):
        with self._settings():
            self.assertFalse(contextual_indexing_enabled("initech", corpus_tokens=199_999))
            self.assertTrue(contextual_indexing_enabled("initech", corpus_tokens=200_000))
            self.assertTrue(contextual_indexing_enabled("initech", corpus_tokens=900_000))

    def test_a_threshold_of_zero_leaves_only_the_explicit_list(self):
        with self._settings(tenants="acme", threshold=0):
            self.assertTrue(contextual_indexing_enabled("acme", corpus_tokens=0))
            self.assertFalse(contextual_indexing_enabled("initech", corpus_tokens=10**9))


try:
    from api import main
    from api.deps import allow_indexing_budget
    HAVE_APP = True
except Exception:
    HAVE_APP = False


class _Counter:
    """The corpus token total, per test instead of per process."""

    def __init__(self, start=None):
        self.value = start

    async def get(self, tenant):
        return self.value

    async def set(self, tenant, value):
        self.value = value

    async def add(self, tenant, amount):
        self.value = (self.value or 0) + amount
        return self.value


@unittest.skipUnless(HAVE_APP and HAVE_DEPS, "fastapi not installed (runs in the venv)")
class BudgetTest(unittest.TestCase):
    """The spend goes through the cap that already exists, and running out
    of it leaves a collection in a state that can be stated."""

    def setUp(self):
        self.charged = []

        class _Budget:
            def __init__(inner, allowed):
                inner.allowed = allowed

            async def allow(inner, tenant, cost=1):
                self.charged.append((tenant, cost))
                return inner.allowed

        self._budget = _Budget

    def _run_ingest(self, budget_allows, contextualized=True):
        chunks = [chunk("a", "doc_0"), chunk("b", "doc_1"), chunk("c", "doc_2")]
        indexed = []

        class _Store:
            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, to_index, tenant):
                indexed.extend(to_index)
                return len(to_index)

            def chunk_counts(self, tenant):
                return {"chunks_total": 3, "chunks_contextualized": 0, "chunks_plain": 3}

            def recount_tokens(self, tenant):
                return 0

        async def _fake_contextualize(document, pending, should_continue=None):
            for c in pending:
                c.context = "situated"
            return len(pending)

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: contextualized), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "explicit"), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter()), \
             mock.patch("api.deps.get_llm_budget", lambda: self._budget(budget_allows)):
            report = run(main._chunk_and_index("doc text", {}, "doc", "acme"))

        return report, chunks, indexed

    def test_one_call_per_chunk_is_charged_before_any_is_made(self):
        report, chunks, indexed = self._run_ingest(budget_allows=True)

        self.assertEqual(self.charged, [("acme", 3)])
        self.assertEqual(report["context_calls"], 3)
        self.assertEqual(report["chunks_contextualized"], 3)
        self.assertEqual(len(indexed), 3)

    def test_the_cap_is_asked_per_batch_and_not_for_the_whole_document(self):
        """
        The cap consumes what it is asked for, refusal included. Asking for
        a whole document up front charged for generations that a stop, or
        the cap itself, then never made, and let one refused run take a
        tenant's renders and chat down for the rest of the hour.
        """
        chunks = [chunk(f"passage {i}", f"doc_{i}") for i in range(120)]
        indexed = []

        class _Store:
            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, batch, tenant):
                indexed.extend(batch)
                return len(batch)

            def chunk_counts(self, tenant):
                return {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}

            def recount_tokens(self, tenant):
                return 0

        async def _fake_contextualize(document, batch, should_continue=None):
            for c in batch:
                c.context = "situated"
            return len(batch)

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter(0)), \
             mock.patch("api.deps.get_llm_budget", lambda: self._budget(True)):
            run(main._chunk_and_index("doc", {}, "doc", "acme"))

        asked = [cost for _, cost in self.charged]
        self.assertEqual(asked, [50, 50, 20], "one ask per batch, never one for 120")
        self.assertEqual(len(indexed), 120)

    def test_running_out_of_budget_partway_indexes_the_rest_plain(self):
        """The declared ending: everything indexed, some of it situated,
        and the response says the cap is what stopped the rest."""
        chunks = [chunk(f"passage {i}", f"doc_{i}") for i in range(120)]
        indexed = []
        situated = []
        allowed = {"left": 1}

        class _Store:
            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, batch, tenant):
                indexed.extend(batch)
                return len(batch)

            def chunk_counts(self, tenant):
                return {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}

            def recount_tokens(self, tenant):
                return 0

        class _Budget:
            async def allow(inner, tenant, cost=1):
                if allowed["left"] <= 0:
                    return False
                allowed["left"] -= 1
                return True

        async def _fake_contextualize(document, batch, should_continue=None):
            situated.extend(c.chunk_id for c in batch)
            for c in batch:
                c.context = "situated"
            return len(batch)

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter(0)), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            report = run(main._chunk_and_index("doc", {}, "doc", "acme"))

        self.assertTrue(report["budget_exceeded"])
        self.assertEqual(len(situated), 50, "only what the cap allowed")
        self.assertEqual(report["chunks_contextualized"], 50)
        self.assertEqual(len(indexed), 120)
        self.assertEqual(report["chunks_indexed"], 120)

    def test_over_the_cap_the_document_is_indexed_without_context(self):
        report, chunks, indexed = self._run_ingest(budget_allows=False)

        self.assertTrue(report["budget_exceeded"])
        self.assertFalse(report["contextual_indexing"])
        self.assertEqual(report["context_calls"], 0)
        self.assertEqual(len(indexed), 3)
        self.assertEqual(report["chunks_indexed"], 3)
        self.assertTrue(all(c.context is None for c in chunks))

    def test_the_estimate_spends_nothing(self):
        chunks = [chunk("a", "doc_0"), chunk("b", "doc_1")]
        indexed = []

        class _Store:
            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, to_index, tenant):
                indexed.extend(to_index)
                return len(to_index)

            def recount_tokens(self, tenant):
                return 0

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "explicit"), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter()), \
             mock.patch("api.deps.get_llm_budget", lambda: self._budget(True)):
            report = run(main._chunk_and_index("doc", {}, "doc", "acme", dry_run=True))

        self.assertEqual(report["status"], "estimated")
        self.assertEqual(report["context_calls"], 2)
        self.assertEqual(report["prompt_cache"], "explicit")
        self.assertEqual(indexed, [])
        self.assertEqual(self.charged, [])

    def _resume_scenario(self, stored_texts, new_texts):
        """A document partly indexed already, uploaded again."""
        chunks = [chunk(t, f"doc_{i}") for i, t in enumerate(new_texts)]
        bought, pruned, indexed = [], [], []

        class _Store:
            def indexed_state(self, source, tenant):
                return {point_id(t): {"contextualized": True} for t in stored_texts}

            def refresh_payloads(self, chunks, stored, tenant):
                return 0

            def index_chunks(self, batch, tenant):
                indexed.extend(c.chunk_id for c in batch)
                return len(batch)

            def prune_removed_chunks(self, source, point_ids, tenant):
                pruned.append(list(point_ids))
                return 0, 0

            def recount_tokens(self, tenant):
                return 0

            def chunk_counts(self, tenant):
                return {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}

        async def _fake_contextualize(document, batch, should_continue=None):
            bought.extend(c.chunk_id for c in batch)
            for c in batch:
                c.context = "situated"
            return len(batch)

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter(0)), \
             mock.patch("api.deps.get_llm_budget", lambda: self._budget(True)):
            report = run(main._chunk_and_index("doc", {}, "doc", "acme"))

        return report, bought, indexed, pruned

    def test_a_corrected_document_is_actually_reindexed(self):
        """
        The one that bites. When a chunk's identity came from its position,
        which survives an edit, a corrected document answered "already
        done": the upload wrote nothing and the index went on answering
        with the text that had been withdrawn.
        """
        report, bought, indexed, _ = self._resume_scenario(
            stored_texts=["first", "second", "third"],
            new_texts=["first", "SECOND, CORRECTED", "third"],
        )

        self.assertEqual(indexed, ["doc_1"], "the corrected chunk is written")
        self.assertEqual(bought, ["doc_1"], "and only that one is paid for")
        self.assertEqual(report["chunks_unchanged"], 2)

    def test_an_identical_upload_costs_nothing(self):
        same = ["first", "second", "third"]
        report, bought, indexed, pruned = self._resume_scenario(same, same)

        self.assertEqual(bought, [], "no generation")
        self.assertEqual(indexed, [], "no embedding, no write")
        self.assertEqual(report["chunks_unchanged"], 3)
        self.assertTrue(pruned, "and the leftovers are still checked")

    def test_pruning_runs_on_a_partly_skipped_upload_and_keeps_the_skipped(self):
        """
        Skipping a chunk as unchanged does not make it a leftover: it is
        still part of this version, so it goes in the set pruning keeps.
        """
        report, _, _, pruned = self._resume_scenario(
            stored_texts=["first", "second"],
            new_texts=["first", "second", "third"],
        )

        self.assertEqual(
            pruned, [[point_id(t) for t in ("first", "second", "third")]],
            "every id of this version, skipped ones included",
        )

    def test_a_resumed_upload_does_not_buy_what_it_already_paid_for(self):
        """An upload that died halfway wrote real chunks: the same text is
        not bought a second time."""
        report, bought, indexed, _ = self._resume_scenario(
            stored_texts=["a", "b"],
            new_texts=["a", "b", "c"],
        )

        self.assertEqual(bought, ["doc_2"], "only the unfinished chunk costs")
        self.assertEqual(self.charged, [("acme", 1)])
        self.assertEqual(report["chunks_unchanged"], 2)
        self.assertEqual(indexed, ["doc_2"])

    def test_a_passage_that_only_moved_is_not_bought_again(self):
        """
        Inserting a section near the top of a document renumbers every
        chunk under it. While a chunk's identity came from that number,
        the whole tail looked new: text that had not changed was embedded
        and situated again, at full price. Identity now comes from the
        text, so only what is genuinely new costs anything.
        """
        report, bought, indexed, _ = self._resume_scenario(
            stored_texts=["first", "second", "third"],
            new_texts=["a new opening", "first", "second", "third"],
        )

        self.assertEqual(bought, ["doc_0"], "only the inserted passage costs")
        self.assertEqual(indexed, ["doc_0"])
        self.assertEqual(report["chunks_unchanged"], 3)

    def test_a_repeated_passage_is_stored_once_per_occurrence(self):
        """
        Boilerplate repeats word for word. Two chunks with the same text
        must not derive the same id, or the second would be written over
        the first and the document would hold fewer points than chunks.
        """
        from rag.vector_store import assign_point_ids

        chunks = [chunk(t, f"doc_{i}") for i, t in enumerate(
            ["Confidential.", "a passage", "Confidential."]
        )]
        assign_point_ids("acme", chunks)

        self.assertEqual(len({c.point_id for c in chunks}), 3)
        self.assertEqual(chunks[0].point_id, point_id("Confidential.", 0))
        self.assertEqual(chunks[2].point_id, point_id("Confidential.", 1))


@unittest.skipUnless(HAVE_APP and HAVE_DEPS, "fastapi not installed (runs in the venv)")
class StoppableIngestTest(unittest.TestCase):
    """
    A run that turns out to be a mistake has to be stoppable, and stopping
    has to keep what has already been paid for. Closing the browser does
    neither: the server is never told it happened.
    """

    def setUp(self):
        # A stopped id stays stopped, so every test runs under its own
        self.ingest_id = uuid.uuid4().hex

    def _run(self, chunk_count, cancel_after=None):
        from rag import ingest_status

        chunks = [chunk(f"passage {i}" * 20, f"doc_{i}") for i in range(chunk_count)]
        indexed = []
        situated = []

        class _Store:
            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, batch, tenant):
                indexed.extend(batch)
                return len(batch)

            def chunk_counts(self, tenant):
                return {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}

            def recount_tokens(self, tenant):
                return 0

        async def _fake_contextualize(document, batch, should_continue=None):
            situated.extend(c.chunk_id for c in batch)
            for c in batch:
                c.context = "situated"
            return len(batch)

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        real_advance = ingest_status.advance

        async def _advance(ingest_id, done, phase=None):
            if cancel_after is not None and done >= cancel_after:
                await ingest_status.cancel(ingest_id, "acme")
            return await real_advance(ingest_id, done, phase)

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter(0)), \
             mock.patch.object(main.ingest_status, "advance", _advance), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            report = run(main._chunk_and_index(
                "document", {}, "doc", "acme", ingest_id=self.ingest_id,
            ))

        return report, indexed, situated

    def test_stopping_keeps_what_was_paid_for_and_buys_no_more(self):
        report, indexed, situated = self._run(200, cancel_after=50)

        self.assertTrue(report["cancelled"])
        self.assertEqual(report["chunks_indexed"], 50)
        self.assertEqual(len(situated), 50, "no generation after the stop")
        self.assertLess(len(indexed), 200)

    def test_a_document_smaller_than_one_batch_can_still_be_stopped(self):
        """
        The flag used to be read only between batches, and most documents
        are one batch: pressing stop on a 10 chunk document did nothing at
        all, the run finished and the answer was "indexed".
        """
        from rag import ingest_status

        chunks = [chunk(f"passage {i}", f"doc_{i}") for i in range(10)]
        situated = []
        indexed = []

        class _Store:
            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, batch, tenant):
                indexed.extend(batch)
                return len(batch)

            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def recount_tokens(self, tenant):
                return 0

            def chunk_counts(self, tenant):
                return {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}

        class _Client:
            prompt_cache = "prefix"

            async def complete_json_cached(inner, system, cached_prefix, user):
                situated.append(user)
                if len(situated) == 3:
                    await ingest_status.cancel("run-small", "acme")
                return '{"context": "situated"}'

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter(0)), \
             mock.patch("rag.contextualizer.create_llm_client", lambda m: _Client()), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            report = run(main._chunk_and_index(
                "document", {}, "doc", "acme", ingest_id="run-small",
            ))

        self.assertTrue(report["cancelled"])
        self.assertLess(len(situated), 10, "the stop must land before the last chunk")
        self.assertEqual(len(indexed), 10)

    def test_a_stop_before_anything_is_indexed_spends_nothing(self):
        """The longest stretch of a big upload is the cutting, which used to
        happen before the run existed: a stop there has to cost zero."""
        from rag import ingest_status

        chunks = [chunk(f"passage {i}", f"doc_{i}") for i in range(10)]
        touched = []

        def _chunk_then_cancel(*args):
            run(ingest_status.cancel("run-early", "acme"))
            return chunks

        class _Store:
            def indexed_state(self, source, tenant):
                touched.append("read")
                return {}

            def index_chunks(self, batch, tenant):
                touched.append("wrote")
                return len(batch)

            def recount_tokens(self, tenant):
                return 0

        with mock.patch.object(main, "_chunk_document", _chunk_then_cancel), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "get_corpus_size", lambda: _Counter(0)):
            report = run(main._chunk_and_index(
                "document", {}, "doc", "acme", ingest_id="run-early",
            ))

        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(report["chunks_indexed"], 0)
        self.assertNotIn("wrote", touched, "nothing indexed after a stop")

    def test_a_stopped_run_reports_the_state_it_left(self):
        from rag import ingest_status

        self._run(200, cancel_after=50)
        status = run(ingest_status.read(self.ingest_id, "acme"))
        self.assertEqual(status["phase"], "cancelled")
        self.assertEqual(status["done"], 50)

    def test_a_run_belongs_to_its_tenant(self):
        """
        The id comes from the client and is the whole key. Without the
        tenant check, one tenant's admin key could watch or stop another
        tenant's run by knowing its id, and every other boundary in this
        codebase is drawn at the tenant.
        """
        from rag import ingest_status

        self._run(60)

        self.assertIsNotNone(run(ingest_status.read(self.ingest_id, "acme")))
        self.assertIsNone(run(ingest_status.read(self.ingest_id, "globex")))
        self.assertFalse(run(ingest_status.cancel(self.ingest_id, "globex")))
        self.assertTrue(run(ingest_status.cancel(self.ingest_id, "acme")))

    def test_an_oversized_id_is_not_a_key(self):
        from rag import ingest_status

        self.assertIsNone(run(ingest_status.read("x" * 500, "acme")))


@unittest.skipUnless(HAVE_APP, "fastapi not installed (runs in the venv)")
class IndexingBudgetExemptionTest(unittest.TestCase):
    def test_indexing_does_not_take_the_admin_exemption(self):
        """
        budget_tenant() exempts admin keys so an operator's own request is
        not throttled. Document routes are admin-only, so reusing it here
        would put thousands of generations outside the cap: the same hole
        already found and closed on the chat endpoint.
        """
        charged = []

        class _Budget:
            async def allow(self, tenant, cost=1):
                charged.append((tenant, cost))
                return True

        with mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            self.assertTrue(run(allow_indexing_budget("acme", 12)))

        self.assertEqual(charged, [("acme", 12)])

    def test_nothing_to_write_costs_nothing(self):
        def _explode():
            raise AssertionError("the budget must not be touched for zero calls")

        with mock.patch("api.deps.get_llm_budget", _explode):
            self.assertTrue(run(allow_indexing_budget("acme", 0)))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_DEPS, "llama_index not installed (runs in the venv)")
class ChunkSizeCeilingTest(unittest.TestCase):
    """
    The semantic splitter cuts where meaning changes and has no size limit,
    so a document whose meaning barely shifts came back as a few enormous
    nodes. One of those fills a whole zone prompt on its own and leaves no
    room for any other result, while scoring a perfect recall.
    """

    def _chunker(self):
        from rag.chunker import SemanticChunker

        class _Embedder:
            model = "test"

            def embed(self, texts):
                return [[0.1, 0.2, 0.3] for _ in texts]

        return SemanticChunker(embed_model=_Embedder())

    def test_a_node_over_the_ceiling_is_cut_and_one_under_it_is_left_alone(self):
        from llama_index.core import Document
        from rag.chunker import CHARS_PER_TOKEN
        from config import settings

        limit = settings.chunk_size * CHARS_PER_TOKEN
        chunker = self._chunker()

        small = Document(text="A short passage. It says one thing.")
        [kept] = chunker.semantic_splitter.get_nodes_from_documents([small])
        self.assertEqual(chunker._within_chunk_size([kept]), [kept],
                         "a node inside the ceiling keeps the boundary meaning chose")

        sentence = "The margin rose again this year for the northern depots. "
        oversized = Document(text=sentence * ((limit * 3) // len(sentence)))
        [big] = chunker.semantic_splitter.get_nodes_from_documents([oversized])
        self.assertGreater(len(big.get_content()), limit)

        pieces = chunker._within_chunk_size([big])
        self.assertGreater(len(pieces), 1, "an oversized node has to be cut")
        self.assertLess(max(len(p.get_content()) for p in pieces),
                        len(big.get_content()))

    def test_offsets_still_point_into_the_document(self):
        """The enrichment windows the document around start_char. Offsets
        relative to the piece just cut would window the wrong place."""
        from llama_index.core import Document
        from rag.chunker import CHARS_PER_TOKEN
        from config import settings

        limit = settings.chunk_size * CHARS_PER_TOKEN
        chunker = self._chunker()
        sentence = "The northern depots reported another increase this quarter. "
        text = sentence * ((limit * 3) // len(sentence))

        [big] = chunker.semantic_splitter.get_nodes_from_documents([Document(text=text)])
        parent = big.start_char_idx or 0
        pieces = chunker._within_chunk_size([big])

        starts = [p.start_char_idx for p in pieces if p.start_char_idx is not None]
        self.assertTrue(starts)
        self.assertTrue(all(s >= parent for s in starts))
        self.assertEqual(starts, sorted(starts), "offsets read in document order")


@unittest.skipUnless(HAVE_DEPS, "app deps not installed (runs in the venv)")
class CancelFlagRaceTest(unittest.TestCase):
    """
    The per-chunk check runs from several coroutines at a time. A check
    that read the record, edited it and wrote it back would eventually put
    a stale copy over a flag that arrived in between, and the stop would be
    lost exactly when someone pressed it.
    """

    def test_asking_whether_to_continue_never_writes(self):
        from rag import ingest_status

        run(ingest_status.begin("race-1", 100, "doc", "acme"))
        run(ingest_status.advance("race-1", 40))
        run(ingest_status.cancel("race-1", "acme"))

        async def hammer():
            return await asyncio.gather(*(ingest_status.cancelled("race-1")
                                          for _ in range(20)))

        self.assertTrue(all(run(hammer())), "every check sees the stop")

        after = run(ingest_status.read("race-1", "acme"))
        self.assertTrue(after["cancelled"], "the checks did not erase the flag")
        self.assertEqual(after["done"], 40, "and did not rewrite the count")
