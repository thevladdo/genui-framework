"""
KB boundary + bring-up behavior of the vector store.

1. The KB tenant boundary is ONE function: QdrantVectorStore._tenant_condition
   (rag/vector_store.py) — every search/list/delete/stats call passes through
   it, and deploy/TENANT-ISOLATION.md cites it as the enforcement point. These
   tests pin its shape so a refactor that weakens the filter breaks loudly.

2. Multi-worker boot race: N fresh workers all see "collection absent" and all
   create it; one wins, the losers get 409 and must treat it as "exists" —
   not fail startup (observed on the deploy compose with WORKERS=4).
"""

import unittest

try:
    from qdrant_client.http import models as qmodels
    from auth.keys import DEFAULT_TENANT
    from rag.vector_store import QdrantVectorStore
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

        stats = store.get_collection_stats()
        self.assertEqual(stats["points_count"], 7)
        self.assertIsNone(stats["vectors_count"])


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
