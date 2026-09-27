"""
When the enrichment applies, and what happens to what was indexed before.

The threshold decides new chunks on its own. The corpus indexed before it
was crossed is the part that breaks quietly: those chunks compete against
enriched ones and lose for a reason that has nothing to do with how
relevant they are, so the state is counted, shown, and fixable by an
operation that nobody starts by accident.

Three properties:

1. Below the threshold new chunks are plain, above it they are enriched,
   and the size is the running total kept while indexing, never a scan.
2. The backfill is idempotent and resumable: a second run after an
   interruption neither duplicates nor skips.
3. Running out of budget halfway leaves a state that can be stated.
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    from rag.contextualizer import estimate_tokens
    from utils.tenant_counter import TenantCounter
    HAVE_DEPS = True
except Exception:
    HAVE_DEPS = False

try:
    from api import main
    HAVE_APP = True
except Exception:
    HAVE_APP = False


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


class _Counter:
    def __init__(self, start=None):
        self.value = start
        self.additions = []

    async def get(self, tenant):
        return self.value

    async def set(self, tenant, value):
        self.value = value

    async def add(self, tenant, amount):
        self.additions.append(amount)
        self.value = (self.value or 0) + amount
        return self.value


class _Chunk:
    """Enough of a SemanticChunk for the ingest path."""

    def __init__(self, content, chunk_id):
        self.content = content
        self.chunk_id = chunk_id
        self.source_document = "doc"
        self.metadata = {}
        self.context = None


@unittest.skipUnless(HAVE_DEPS, "app deps not installed (runs in the venv)")
class TokenCountTest(unittest.TestCase):
    def test_the_size_is_counted_in_tokens_not_documents_or_points(self):
        self.assertEqual(estimate_tokens("a" * 4000), 1000)
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens(None), 0)

    def test_nothing_counted_is_not_the_same_as_counted_zero(self):
        """None means rebuild from the collection. Zero would mean a corpus
        that never reaches the threshold and a feature that never starts."""
        counter = TenantCounter(key_prefix="genui:test2:")
        self.assertIsNone(run(counter.get("acme")))
        run(counter.set("acme", 0))
        self.assertEqual(run(counter.get("acme")), 0)


@unittest.skipUnless(HAVE_APP and HAVE_DEPS, "fastapi not installed (runs in the venv)")
class ThresholdAtIngestTest(unittest.TestCase):
    """Sub-threshold indexes plain, over-threshold indexes enriched, and the
    total comes from the counter rather than from a scan."""

    def _ingest(self, corpus_tokens, chunk_chars=400, threshold=200_000):
        chunks = [_Chunk("x" * chunk_chars, f"doc_{i}") for i in range(3)]
        counter = _Counter(corpus_tokens)
        scanned = []
        situated = []

        class _Store:
            def prune_removed_chunks(self, source, chunk_ids, tenant):
                return 0, 0

            def indexed_state(self, source, tenant):
                return {}

            def index_chunks(self, to_index, tenant):
                return len(to_index)

            def chunk_counts(self, tenant):
                return {"chunks_total": 40, "chunks_contextualized": 3, "chunks_plain": 37}

            def recount_tokens(self, tenant):
                scanned.append(tenant)
                return 0

        async def _fake_contextualize(document, pending, should_continue=None):
            situated.extend(c.chunk_id for c in pending)
            for c in pending:
                c.context = "situated"
            return len(pending)

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        with mock.patch.object(main, "_chunk_document", lambda *a: chunks), \
             mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "get_corpus_size", lambda: counter), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main.settings, "contextual_indexing_threshold_tokens", threshold), \
             mock.patch.object(main.settings, "contextual_indexing_tenants", ""), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            report = run(main._chunk_and_index("document", {}, "doc", "acme"))

        return report, counter, situated, scanned

    def test_below_the_threshold_new_chunks_are_indexed_plain(self):
        report, counter, situated, _ = self._ingest(corpus_tokens=1_000)

        self.assertFalse(report["contextual_indexing"])
        self.assertEqual(report["context_calls"], 0)
        self.assertEqual(situated, [])

    def test_above_the_threshold_new_chunks_are_enriched_with_nobody_switching_it_on(self):
        report, counter, situated, _ = self._ingest(corpus_tokens=500_000)

        self.assertTrue(report["contextual_indexing"])
        self.assertEqual(report["context_calls"], 3)
        self.assertEqual(len(situated), 3)

    def test_the_upload_that_crosses_the_line_is_itself_enriched_and_says_so(self):
        report, counter, situated, _ = self._ingest(corpus_tokens=199_800)

        self.assertTrue(report["crosses_threshold"])
        self.assertTrue(report["contextual_indexing"])
        self.assertEqual(len(situated), 3)
        self.assertEqual(report["chunks_left_behind"], 37)

    def test_an_upload_well_inside_the_corpus_does_not_report_a_crossing(self):
        report, _, _, _ = self._ingest(corpus_tokens=500_000)
        self.assertFalse(report["crosses_threshold"])

        report, _, _, _ = self._ingest(corpus_tokens=1_000)
        self.assertFalse(report["crosses_threshold"])

    def test_the_size_is_updated_by_indexing_and_never_recomputed(self):
        report, counter, _, scanned = self._ingest(corpus_tokens=1_000)

        self.assertEqual(counter.additions, [300], "3 chunks of 400 chars")
        self.assertEqual(counter.value, 1_300)
        self.assertEqual(scanned, [], "a known total must not trigger a scan")

    def test_a_total_that_was_never_counted_is_rebuilt_once(self):
        report, counter, _, scanned = self._ingest(corpus_tokens=None)

        self.assertEqual(scanned, ["acme"], "rebuilt from the collection")
        self.assertEqual(counter.value, 300, "and carries on from there")


@unittest.skipUnless(HAVE_DEPS, "app deps not installed (runs in the venv)")
class PointIdentityTest(unittest.TestCase):
    """
    A point id drawn at random made every upload an insert, so uploading a
    document twice stored it twice and one passage answered under two
    points. Derived from the text the chunk holds, the second upload
    overwrites the first.
    """

    def test_a_passage_is_not_shared_across_tenants(self):
        from rag.vector_store import content_hash, point_id_for

        digest = content_hash("a passage")
        self.assertNotEqual(
            point_id_for("acme", "report", digest),
            point_id_for("globex", "report", digest),
        )

    def test_the_same_passage_in_two_documents_is_two_points(self):
        """Documents are deleted and pruned one at a time: sharing a point
        would take a passage out of a document nobody touched."""
        from rag.vector_store import content_hash, point_id_for

        digest = content_hash("a passage")
        self.assertNotEqual(
            point_id_for("acme", "report", digest),
            point_id_for("acme", "handbook", digest),
        )

    def test_the_default_tenant_and_no_tenant_are_the_same_point(self):
        """Legacy documents carry no tenant and belong to the default one:
        they must not gain a second copy the first time one is named."""
        from auth.keys import DEFAULT_TENANT
        from rag.vector_store import content_hash, point_id_for

        digest = content_hash("a passage")
        self.assertEqual(
            point_id_for(None, "report", digest),
            point_id_for(DEFAULT_TENANT, "report", digest),
        )


@unittest.skipUnless(HAVE_APP and HAVE_DEPS, "fastapi not installed (runs in the venv)")
class DeleteAccountingTest(unittest.TestCase):
    """A document that left has to take its tokens with it, or the total
    only grows and a corpus that shrank keeps paying to index with context."""

    def _delete(self, removed_tokens):
        counter = _Counter(50_000)

        class _Store:
            def delete_by_source(self, source, tenant):
                return removed_tokens

        auth = SimpleNamespace(tenant="acme", is_admin=True, key_fingerprint="k")

        with mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "get_corpus_size", lambda: counter):
            result = run(main.delete_document("doc", auth))

        return result, counter

    def test_the_tokens_of_a_deleted_document_leave_the_total(self):
        result, counter = self._delete(removed_tokens=12_000)

        self.assertEqual(result["status"], "deleted")
        self.assertEqual(counter.additions, [-12_000])
        self.assertEqual(counter.value, 38_000)

    def test_a_deletion_that_removed_nothing_leaves_the_total_alone(self):
        result, counter = self._delete(removed_tokens=0)
        self.assertEqual(counter.additions, [])

    def test_a_failed_deletion_is_an_error_and_changes_no_total(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            self._delete(removed_tokens=-1)

    def test_the_total_never_goes_below_empty(self):
        from utils.tenant_counter import TenantCounter

        counter = TenantCounter(key_prefix="genui:test3:")
        run(counter.set("acme", 100))
        run(counter.add("acme", -500))
        self.assertEqual(run(counter.get("acme")), 0)


@unittest.skipUnless(HAVE_APP and HAVE_DEPS, "fastapi not installed (runs in the venv)")
class BackfillTest(unittest.TestCase):
    """The operation that brings the corpus indexed before the line up to
    the rest. Never automatic, priced first, resumable."""

    def setUp(self):
        self.charged = []

    def _backfill(self, plain_points, budget_allows=True, dry_run=False,
                  fails_after=None):
        """Runs the route against a store that behaves like Qdrant: a point
        updated in place stops being plain."""
        state = {point["id"]: dict(point, contextualized=False) for point in plain_points}
        charged = self.charged

        class _Store:
            def plain_points(self, tenant, max_points):
                return [
                    {k: v for k, v in point.items() if k != "contextualized"}
                    for point in state.values()
                    if not point["contextualized"]
                ][:max_points]

            def chunk_counts(self, tenant):
                plain = sum(1 for p in state.values() if not p["contextualized"])
                return {
                    "chunks_total": len(state),
                    "chunks_contextualized": len(state) - plain,
                    "chunks_plain": plain,
                }

            def recontextualize(self, chunks, point_ids):
                done = 0
                for chunk, point_id in zip(chunks, point_ids):
                    if not chunk.context:
                        continue
                    state[point_id]["contextualized"] = True
                    done += 1
                return done

        written = []

        async def _fake_contextualize(document, chunks, should_continue=None):
            for i, c in enumerate(chunks):
                if fails_after is not None and len(written) >= fails_after:
                    continue
                c.context = "situated"
                written.append(c.chunk_id)
            return len(written)

        class _Budget:
            async def allow(self, tenant, cost=1):
                charged.append((tenant, cost))
                return budget_allows

        auth = SimpleNamespace(tenant="acme", is_admin=True, key_fingerprint="k")
        request = main.BackfillRequest(dry_run=dry_run, max_chunks=500)

        with mock.patch.object(main, "get_vector_store", lambda: _Store()), \
             mock.patch.object(main, "contextualize", _fake_contextualize), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            report = run(main.backfill_context(request, auth))

        return report, state, written

    def _points(self, n, source="doc"):
        return [
            {"id": i, "chunk_id": f"{source}_{i}", "source_document": source,
             "content": f"passage {i}"}
            for i in range(n)
        ]

    def test_the_estimate_spends_nothing(self):
        report, state, written = self._backfill(self._points(4), dry_run=True)

        self.assertEqual(report["status"], "estimated")
        self.assertEqual(report["context_calls"], 4)
        self.assertEqual(written, [])
        self.assertEqual(self.charged, [])
        self.assertTrue(all(not p["contextualized"] for p in state.values()))

    def test_a_second_run_after_an_interruption_neither_duplicates_nor_skips(self):
        points = self._points(5)

        first, state, written = self._backfill(points, fails_after=2)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["chunks_contextualized"], 2)
        self.assertEqual(first["chunks_plain_remaining"], 3)

        done_after_first = {i for i, p in state.items() if p["contextualized"]}
        self.assertEqual(len(done_after_first), 2)

        second, state2, written2 = self._backfill(
            [{k: v for k, v in p.items() if k != "contextualized"}
             for p in state.values() if not p["contextualized"]]
        )
        self.assertEqual(second["chunks_contextualized"], 3)
        self.assertEqual(second["status"], "completed")
        self.assertEqual(len(state2), 3, "no point was duplicated")
        self.assertTrue(all(p["contextualized"] for p in state2.values()))

    def test_running_it_again_when_there_is_nothing_left_costs_nothing(self):
        report, state, written = self._backfill([])

        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["chunks_contextualized"], 0)
        self.assertEqual(self.charged, [], "an empty run must not touch the cap")

    def test_a_refused_run_asks_for_one_batch_not_the_whole_job(self):
        """
        The cap CONSUMES what it is asked for, even when it refuses. Asking
        for a whole run up front meant one refused backfill could eat a
        tenant's entire hour, taking zone renders and chat down with it.
        """
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as raised:
            self._backfill(self._points(600), budget_allows=False)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Nothing was indexed", raised.exception.detail)

        asked = [cost for _, cost in self.charged]
        self.assertEqual(asked, [main._INGEST_BATCH],
                         "one batch asked for, then it stops")
        self.assertLess(sum(asked), 600)

    def test_a_document_is_rebuilt_from_its_chunks_in_reading_order(self):
        seen = {}

        async def _capture(document, chunks, should_continue=None):
            seen["document"] = document
            for c in chunks:
                c.context = "situated"
            return len(chunks)

        class _Store:
            def recontextualize(self, chunks, point_ids):
                return len(chunks)

        # Past ten chunks the index has to be read as a number: 
        # sorted as text, doc_10 comes before doc_2 
        # and the document is rebuilt with its middle at the top
        order = [7, 11, 0, 3, 10, 1, 9, 2, 8, 4, 6, 5]
        shuffled = [
            {"id": i, "chunk_id": f"doc_{i}", "source_document": "doc",
             "content": f"passage {i}"}
            for i in order
        ]

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        with mock.patch.object(main, "contextualize", _capture), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            run(main._backfill_documents(_Store(), shuffled, "acme"))

        self.assertEqual(
            seen["document"],
            "\n\n".join(f"passage {i}" for i in range(12)),
        )


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_APP and HAVE_DEPS, "fastapi not installed (runs in the venv)")
class BackfillStopTest(unittest.TestCase):
    """
    The dialog offering this says it can be stopped. It could not: the run
    went to the end of whatever it had been given, spending on every chunk.
    """

    def test_a_running_backfill_stops_between_batches(self):
        from rag import ingest_status

        points = [
            {"id": i, "chunk_id": f"doc_{i}", "source_document": "doc",
             "content": f"passage {i}"}
            for i in range(200)
        ]
        situated = []

        class _Store:
            def recontextualize(self, chunks, ids):
                return len(chunks)

        async def _contextualize(document, chunks, should_continue=None):
            situated.extend(c.chunk_id for c in chunks)
            if len(situated) >= main._INGEST_BATCH:
                await ingest_status.cancel("bf-1", "acme")
            return len(chunks)

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        run(ingest_status.begin("bf-1", len(points), "backfill", "acme"))
        with mock.patch.object(main, "contextualize", _contextualize), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            done, on_budget = run(
                main._backfill_documents(_Store(), points, "acme", "bf-1")
            )

        self.assertFalse(on_budget, "the cap is not what stopped it")
        self.assertLess(len(situated), len(points), "it stopped before the end")
        self.assertEqual(done, main._INGEST_BATCH, "and kept the batch it finished")

    def test_without_an_id_a_backfill_still_runs(self):
        """The id is optional: an API caller that omits it gets the old
        behaviour rather than a run that cannot start."""
        points = [{"id": 0, "chunk_id": "doc_0", "source_document": "doc",
                   "content": "a passage"}]

        class _Store:
            def recontextualize(self, chunks, ids):
                return len(chunks)

        async def _contextualize(document, chunks, should_continue=None):
            return len(chunks)

        class _Budget:
            async def allow(self, tenant, cost=1):
                return True

        with mock.patch.object(main, "contextualize", _contextualize), \
             mock.patch("api.deps.get_llm_budget", lambda: _Budget()):
            done, _ = run(main._backfill_documents(_Store(), points, "acme"))

        self.assertEqual(done, 1)
