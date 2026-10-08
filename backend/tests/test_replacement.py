"""
Replacing a document already in the knowledge base.

The ingest path and the real vector store run together against an
in-memory collection, so what is asserted is what the index holds:

1. A new version that cannot be stored in full prunes nothing, says so, and
   the old version stays retrievable.
2. Identical text under corrected metadata rewrites the payload and embeds
   nothing.
3. The corpus total moves by what entered and left: upload, corrected
   upload and delete bring it back to zero, and writing context onto text
   already stored adds nothing.
"""

import asyncio
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

from memory_stores import use_memory_stores

try:
    from qdrant_client.http import models as qmodels
    from auth.keys import AuthContext
    from rag.chunker import SemanticChunk
    from rag.contextualizer import estimate_tokens
    from rag.vector_store import QdrantVectorStore, payload_signature
    from api import main
    HAVE_APP = True
except Exception:
    HAVE_APP = False


def setUpModule():
    use_memory_stores()


def run(coro):
    return asyncio.run(coro)


def _matches(condition, point):
    if isinstance(condition, qmodels.FieldCondition):
        return point.payload.get(condition.key) == condition.match.value
    if isinstance(condition, qmodels.HasIdCondition):
        return point.id in {str(i) for i in condition.has_id}
    if isinstance(condition, qmodels.Filter):
        return (
            all(_matches(c, point) for c in condition.must or [])
            and not any(_matches(c, point) for c in condition.must_not or [])
            and (not condition.should or any(_matches(c, point) for c in condition.should))
        )
    raise AssertionError(f"condition the fake does not know: {condition!r}")


class _Collection:
    """The part of the Qdrant client the write path uses, over a dict."""

    def __init__(self):
        self.points = {}
        self.failing_delete = False

    def upsert(self, collection_name, points):
        for point in points:
            self.points[str(point.id)] = SimpleNamespace(id=str(point.id), payload=dict(point.payload))

    def scroll(self, collection_name, scroll_filter, limit, offset, with_payload, with_vectors):
        found = []
        for point in self.points.values():
            if not _matches(scroll_filter, point):
                continue
            if isinstance(with_payload, list):
                payload = {k: v for k, v in point.payload.items() if k in with_payload}
            else:
                payload = {k: v for k, v in point.payload.items() if k not in with_payload.exclude}
            found.append(SimpleNamespace(id=point.id, payload=payload))
        return found, None

    def delete(self, collection_name, points_selector):
        if self.failing_delete:
            raise RuntimeError("vector database unavailable")
        if isinstance(points_selector, qmodels.PointIdsList):
            doomed = {str(i) for i in points_selector.points}
        else:
            doomed = {i for i, p in self.points.items() if _matches(points_selector.filter, p)}
        for point_id in doomed:
            self.points.pop(point_id, None)

    def batch_update_points(self, collection_name, update_operations):
        for operation in update_operations:
            write = operation.overwrite_payload
            for point_id in write.points:
                self.points[str(point_id)].payload = dict(write.payload)


class _Embedder:
    model = "test-embedding"

    def __init__(self):
        self.calls = 0
        self.failing = False

    def embed(self, texts):
        self.calls += 1
        if self.failing:
            raise RuntimeError("embedding provider unavailable")
        return [[0.1, 0.2, 0.3] for _ in texts]


class _Counter:
    """The corpus total, unclamped so that a wrong subtraction shows."""

    def __init__(self):
        self.value = None

    async def get(self, tenant):
        return self.value

    async def set(self, tenant, value):
        self.value = value

    async def add(self, tenant, amount):
        self.value = (self.value or 0) + amount
        return self.value


@unittest.skipUnless(HAVE_APP, "app deps not installed (runs in the venv)")
class ReplacementTest(unittest.TestCase):
    def setUp(self):
        self.store = QdrantVectorStore.__new__(QdrantVectorStore)
        self.store.collection_name = "genui_documents"
        self.store.client = _Collection()
        self.store.embed_model = _Embedder()
        self.store._collection_dim = 3
        self.store.has_lexical = False
        self.store.hybrid = False
        self.counter = _Counter()

        for patcher in (
            mock.patch.object(main, "get_vector_store", lambda: self.store),
            mock.patch.object(main, "get_corpus_size", lambda: self.counter),
            mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def upload(self, texts, url="https://acme.example/policy"):
        def _cut(text, metadata, source_name, estimate=False):
            return [
                SemanticChunk(
                    content=content,
                    # What the splitter adds is drawn anew on every cut
                    metadata={**metadata, "node_id": str(uuid.uuid4())},
                    chunk_id=f"{source_name}_{i}",
                    source_document=source_name,
                )
                for i, content in enumerate(texts)
            ]

        with mock.patch.object(main, "_chunk_document", _cut):
            return run(main._chunk_and_index(
                "\n\n".join(texts), {"title": "Policy", "url": url}, "policy", "acme",
            ))

    def stored(self):
        return sorted(
            (p.payload["content"], p.payload.get("url"))
            for p in self.store.client.points.values()
        )

    def test_a_failed_replacement_keeps_the_version_it_was_replacing(self):
        self.upload(["Cap is 4 percent.", "Fees are waived.", "Terms apply."])
        self.store.embed_model.failing = True

        report = self.upload(["Cap is 5 percent.", "Fees are waived.", "Terms apply."])

        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["chunks_pruned"], 0)
        self.assertEqual(report["chunks_failed"], 1)
        self.assertTrue(report["previous_version_served"])
        self.assertIn("indexing failed after 0 of 1 chunks", report["error"])
        self.assertNotIn("embedding provider unavailable", report["error"])
        self.assertIn(
            "Cap is 4 percent.", [content for content, _ in self.stored()],
            "the old passage answers until its replacement is stored",
        )

        self.store.embed_model.failing = False
        retried = self.upload(["Cap is 5 percent.", "Fees are waived.", "Terms apply."])
        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["chunks_pruned"], 1)
        self.assertEqual(
            [content for content, _ in self.stored()],
            ["Cap is 5 percent.", "Fees are waived.", "Terms apply."],
        )

    def test_a_prune_that_fails_is_not_reported_as_completed(self):
        self.upload(["Cap is 4 percent.", "Fees are waived."])
        self.store.client.failing_delete = True

        report = self.upload(["Cap is 5 percent.", "Fees are waived."])

        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["chunks_pruned"], 0)
        self.assertTrue(report["previous_version_served"])
        self.assertIn("removing the previous version failed", report["error"])
        self.assertNotIn("vector database unavailable", report["error"])
        self.assertIn(
            "Cap is 4 percent.", [content for content, _ in self.stored()],
            "the withdrawn passage is still in the index, and the report has to say so",
        )

        self.store.client.failing_delete = False
        retried = self.upload(["Cap is 5 percent.", "Fees are waived."])
        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["chunks_pruned"], 1)
        self.assertEqual(
            self.counter.value,
            estimate_tokens("Cap is 5 percent.") + estimate_tokens("Fees are waived."),
        )

    def test_a_corrected_url_reaches_the_payload_without_embedding(self):
        texts = ["Cap is 4 percent.", "Fees are waived."]
        self.upload(texts, url="https://acme.example/old")
        calls = self.store.embed_model.calls

        report = self.upload(texts, url="https://acme.example/new")

        self.assertEqual(self.store.embed_model.calls, calls, "no embedding for a metadata change")
        self.assertEqual(report["chunks_payload_updated"], 2)
        self.assertEqual(report["chunks_indexed"], 0)
        self.assertEqual({url for _, url in self.stored()}, {"https://acme.example/new"})

        again = self.upload(texts, url="https://acme.example/new")
        self.assertEqual(
            again["chunks_payload_updated"], 0,
            "upload time and splitter node ids are not a change of metadata",
        )

    def test_the_signature_ignores_key_order_and_sequence_type(self):
        self.assertEqual(
            payload_signature({"url": "u", "tags": ("a", "b")}),
            payload_signature({"tags": ["a", "b"], "url": "u"}),
        )

    def test_upload_corrected_upload_and_delete_bring_the_total_back_to_zero(self):
        first = ["Cap is 4 percent.", "Fees are waived.", "Terms apply."]
        self.upload(first)
        self.assertEqual(self.counter.value, sum(estimate_tokens(t) for t in first))

        second = ["Cap is 5 percent, from March onwards.", "Fees are waived.", "Terms apply."]
        self.upload(second)
        self.assertEqual(self.counter.value, sum(estimate_tokens(t) for t in second))

        auth = AuthContext(tenant="acme", is_admin=True, key_fingerprint="test")
        with mock.patch.object(main, "get_audit_logger", lambda: mock.Mock()):
            run(main.delete_document("policy", auth=auth))
        self.assertEqual(self.store.client.points, {})
        self.assertEqual(self.counter.value, 0)

    def test_writing_context_onto_stored_text_counts_nothing(self):
        texts = ["Cap is 4 percent.", "Fees are waived."]
        self.upload(texts)
        before = self.counter.value

        async def _situate(document, batch, should_continue=None):
            for c in batch:
                c.context = "situated"
            return len(batch)

        budget = SimpleNamespace(allow=mock.AsyncMock(return_value=True))
        with mock.patch.object(main, "contextual_indexing_enabled", lambda t, n=0: True), \
             mock.patch.object(main, "contextualize", _situate), \
             mock.patch.object(main, "prompt_cache_mode", lambda: "prefix"), \
             mock.patch.object(main.settings, "contextual_indexing_threshold_tokens", before + 1), \
             mock.patch("api.deps.get_llm_budget", lambda: budget):
            report = self.upload(texts)

        self.assertEqual(report["chunks_contextualized"], 2)
        self.assertEqual(self.counter.value, before)
        self.assertEqual(report["corpus_tokens_after"], before)
        self.assertFalse(
            report["crosses_threshold"],
            "text already stored cannot be what takes the corpus over the threshold",
        )


if __name__ == "__main__":
    unittest.main()
