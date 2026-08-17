"""
KB boundary + bring-up behavior of the vector store.

1. The KB tenant boundary is ONE function: QdrantVectorStore._tenant_condition
   (rag/vector_store.py) — every search/list/delete/stats call passes through
   it, and deploy/TENANT-ISOLATION.md cites it as the enforcement point. These
   tests pin its shape so a refactor that weakens the filter breaks loudly.
   Hybrid search adds a second branch to every query, and the filter has to
   ride on that one too: a lexical branch without it is a leak across
   tenants, not a relevance defect.

2. Multi-worker boot race: N fresh workers all see "collection absent" and all
   create it; one wins, the losers get 409 and must treat it as "exists" —
   not fail startup (observed on the deploy compose with WORKERS=4).

3. A collection created before the lexical vector existed cannot gain it, so
   it must keep serving dense-only searches instead of failing.
"""

import asyncio
import unittest

try:
    from qdrant_client.http import models as qmodels
    from auth.keys import DEFAULT_TENANT
    from rag.vector_store import LEXICAL_VECTOR, QdrantVectorStore, lexical_vector
    HAVE_DEPS = True
except Exception:  # qdrant-client / llama_index not in the shell python
    HAVE_DEPS = False


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class TenantConditionTest(unittest.TestCase):
    def _condition(self, tenant):
        # __new__: the builder touches no instance state, and __init__ would
        # connect to Qdrant
        store = QdrantVectorStore.__new__(QdrantVectorStore)
        return store._tenant_condition(tenant)

    def test_named_tenant_is_strict_equality(self):
        """A named tenant must NEVER match legacy points missing the field."""
        cond = self._condition("agente")
        self.assertIsInstance(cond, qmodels.FieldCondition)
        self.assertEqual(cond.key, "tenant")
        self.assertEqual(cond.match.value, "agente")

    def test_default_tenant_also_matches_legacy_points(self):
        """Default tenant = its own points + pre-isolation points (no field)."""
        cond = self._condition(None)
        self.assertIsInstance(cond, qmodels.Filter)
        self.assertIsNone(cond.must)
        self.assertEqual(len(cond.should), 2)

        field = [c for c in cond.should if isinstance(c, qmodels.FieldCondition)]
        empty = [c for c in cond.should if isinstance(c, qmodels.IsEmptyCondition)]
        self.assertEqual(len(field), 1)
        self.assertEqual(field[0].key, "tenant")
        self.assertEqual(field[0].match.value, DEFAULT_TENANT)
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0].is_empty.key, "tenant")

    def test_explicit_default_equals_none(self):
        self.assertEqual(
            self._condition(DEFAULT_TENANT).model_dump(),
            self._condition(None).model_dump(),
        )


class _FakeEmbedder:
    model = "text-embedding-3-small"

    @property
    def dimension(self):
        return 1536

    def dimension_if_known(self):
        return 1536


class _LostRaceClient:
    """Fresh Qdrant as seen by a worker that loses the create race."""

    def get_collections(self):
        class _Cols:
            collections = []
        return _Cols()

    def create_collection(self, **kwargs):
        raise Exception(
            'Unexpected Response: 409 (Conflict)\nRaw response content:\n'
            'b\'{"status":{"error":"Wrong input: Collection `genui_documents` '
            'already exists!"}}\''
        )

    def get_collection(self, name):
        class _V:
            size = 1536

        class _P:
            vectors = _V()

        class _C:
            params = _P()

        class _Info:
            config = _C()
        return _Info()

    def create_payload_index(self, **kwargs):
        # The race winner already created the indices
        raise Exception("Index already exists")


class _CapturingAsyncClient:
    """Records the query it was asked to run and returns one hit."""

    def __init__(self):
        self.call = None

    async def query_points(self, **kwargs):
        self.call = kwargs

        class _Hit:
            score = 0.5
            payload = {"content": "a passage", "chunk_id": "c1", "tenant": "acme"}

        class _Result:
            points = [_Hit()]

        return _Result()


def _searchable_store(hybrid):
    """A store wired for search_async and nothing else: no Qdrant, no network."""
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.collection_name = "genui_documents"
    store.hybrid = hybrid
    store.has_lexical = hybrid
    store._collection_dim = None
    store.embed_model = _SearchEmbedder()
    store.async_client = _CapturingAsyncClient()
    return store


class _SearchEmbedder:
    model = "text-embedding-3-small"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class HybridSearchTest(unittest.TestCase):
    def test_tenant_filter_rides_on_both_branches(self):
        """
        The lexical branch selects candidates on its own. A filter applied
        only to the dense one would let another tenant's chunk in through
        the side that nobody looked at.
        """
        store = _searchable_store(hybrid=True)
        results = asyncio.run(store.search_async(query="fuel adjustment cap", tenant="acme"))
        self.assertEqual(len(results), 1)

        call = store.async_client.call
        branches = call["prefetch"]
        self.assertEqual(len(branches), 2, "expected a dense and a lexical branch")
        self.assertEqual({b.using for b in branches}, {"", LEXICAL_VECTOR})

        for branch in branches:
            conditions = branch.filter.must
            tenant_conditions = [
                c for c in conditions
                if isinstance(c, qmodels.FieldCondition) and c.key == "tenant"
            ]
            self.assertEqual(len(tenant_conditions), 1, f"{branch.using or 'dense'} branch")
            self.assertEqual(tenant_conditions[0].match.value, "acme")

        self.assertIsInstance(call["query"], qmodels.FusionQuery)

    def test_similarity_threshold_stays_on_the_dense_branch(self):
        """
        The fused score is a rank score. Cutting it with a cosine threshold
        would empty every result set, so the setting rides where it means
        what it was configured to mean.
        """
        store = _searchable_store(hybrid=True)
        asyncio.run(store.search_async(query="fuel adjustment cap", score_threshold=0.42))

        branches = {b.using: b for b in store.async_client.call["prefetch"]}
        self.assertEqual(branches[""].score_threshold, 0.42)
        self.assertIsNone(branches[LEXICAL_VECTOR].score_threshold)
        self.assertIsNone(store.async_client.call.get("score_threshold"))

    def test_collection_without_the_lexical_vector_still_serves_searches(self):
        """A collection created before hybrid existed cannot gain the vector:
        it must keep answering, densely, instead of failing."""
        store = _searchable_store(hybrid=False)
        results = asyncio.run(store.search_async(query="fuel adjustment cap", tenant="acme"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content, "a passage")

        call = store.async_client.call
        self.assertNotIn("prefetch", call)
        self.assertEqual(call["query"], [0.1, 0.2, 0.3])
        self.assertIn("query_filter", call)

    def test_a_query_with_no_usable_term_keeps_the_dense_branch(self):
        store = _searchable_store(hybrid=True)
        asyncio.run(store.search_async(query="?! ..."))

        branches = store.async_client.call["prefetch"]
        self.assertEqual([b.using for b in branches], [""])

    def test_lexical_vector_is_stable_across_processes(self):
        """
        A chunk is indexed in one process and queried from another. A
        randomized hash (which is what Python's own hash() is) would file
        the same term under two different slots and the branch would match
        nothing, quietly.
        """
        indexed = lexical_vector("Guaranteed First Response, or GFR")
        queried = lexical_vector("what does gfr mean")
        self.assertIn(1064687750, indexed.indices)
        self.assertIn(1064687750, queried.indices)

        counted = lexical_vector("margin a margin rose")
        self.assertEqual(dict(zip(counted.indices, counted.values))[862046937], 2.0)
        self.assertEqual(len(counted.indices), 2)


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class CollectionStatsCompatTest(unittest.TestCase):
    def test_stats_survive_clients_without_vectors_count(self):
        """
        qdrant-client >= 1.18 dropped CollectionInfo.vectors_count: stats
        (and the /health probe built on them) must not turn into {} on a
        healthy modern stack.
        """
        class _Info:
            points_count = 7
            status = "green"
            # no vectors_count / indexed_vectors_count attributes

        class _Client:
            def get_collection(self, name):
                return _Info()

        store = QdrantVectorStore.__new__(QdrantVectorStore)
        store.collection_name = "genui_documents"
        store.client = _Client()
        store.hybrid = False

        stats = store.get_collection_stats()
        self.assertEqual(stats["points_count"], 7)
        self.assertIsNone(stats["vectors_count"])
        self.assertEqual(stats["retrieval_mode"], "dense")


@unittest.skipUnless(HAVE_DEPS, "qdrant-client not installed (runs in the venv)")
class CollectionCreateRaceTest(unittest.TestCase):
    def test_losing_the_create_race_is_not_a_startup_failure(self):
        store = QdrantVectorStore.__new__(QdrantVectorStore)
        store.collection_name = "genui_documents"
        store.client = _LostRaceClient()
        store.embed_model = _FakeEmbedder()
        store._collection_dim = None

        store._ensure_collection()  # must not raise: 409 = another worker won

        # The loser validates the existing collection like any other boot
        self.assertEqual(store._collection_dim, 1536)


if __name__ == "__main__":
    unittest.main()
