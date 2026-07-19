"""
Tests for BYOK embeddings.

The failure these tests pin down: the LLM was already pluggable
(LLM_PROVIDER + OPENAI_BASE_URL) but embeddings were hardwired to
llama_index's OpenAIEmbedding with NO base_url. An operator running an
all-local LLM still sent every document chunk and every search query to
api.openai.com — silently. And with no OpenAI key, the failure was mute:
search returned [], index skipped batches, zones rendered without RAG.
qdrant_vector_size=1536 (OpenAI's dimension) was a constant, so a local
model with a different dimension corrupted or broke the index quietly.

The contract after the fix:
- embeddings are selected via config exactly like the LLM client, and an
  OpenAI-compatible base_url keeps them in-house;
- an unconfigured embedding raises an operator-readable error — there is
  NO silent fallback to OpenAI, ever;
- the Qdrant vector size derives from the embedding model; an existing
  collection with a different dimension raises a clear error instead of
  silently degrading.

No SDK, no network: openai / qdrant / llama_index / config are replaced
in sys.modules by controllable fakes where needed.
"""

import asyncio
import importlib
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from llm.embeddings import (
    EmbeddingClient,
    EmbeddingConfigError,
    create_embedding_client,
    resolve_embedding_config,
)
from llm.factory import GEMINI_OPENAI_BASE_URL

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def run(coro):
    return asyncio.run(coro)


# Reusable fakes


class MockEmbedder(EmbeddingClient):
    """Deterministic embedder: no SDK, no network, counts its calls."""

    def __init__(self, model="mock-embed", dim=768, dimensions=None):
        self.model = model
        self.declared_dimensions = dimensions
        self._dim = dim
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        vectors = []
        for i, _ in enumerate(texts):
            vec = [0.0] * self._dim
            vec[i % self._dim] = 1.0  # varied unit vectors (cosine-safe)
            vectors.append(vec)
        return vectors


class FakeEmbeddingsAPI:
    def __init__(self, dim=32):
        self.dim = dim
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        texts = kwargs["input"]
        # Data returned in REVERSED order: the client must sort by index
        data = [
            SimpleNamespace(index=i, embedding=[float(i)] * self.dim)
            for i in range(len(texts))
        ]
        return SimpleNamespace(data=list(reversed(data)))


class FakeOpenAI:
    last_instance = None

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        self.embeddings = FakeEmbeddingsAPI()
        FakeOpenAI.last_instance = self


def fake_openai_module():
    module = types.ModuleType("openai")
    module.OpenAI = FakeOpenAI
    return module


def fake_settings(**overrides):
    """A config.settings stand-in with every attr the RAG path touches."""
    values = dict(
        embedding_provider="openai",
        embedding_model="mock-embed",
        embedding_api_key=None,
        embedding_base_url=None,
        embedding_dimensions=None,
        openai_api_key=None,
        openai_base_url=None,
        google_api_key=None,
        llm_timeout_seconds=None,
        qdrant_host="localhost",
        qdrant_port=6333,
        qdrant_collection="test_collection",
        top_k_retrieval=5,
        similarity_threshold=0.35,
        use_semantic_chunking=True,
        breakpoint_percentile_threshold=95,
        buffer_size=1,
        chunk_size=512,
        chunk_overlap=50,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_config_module(settings_ns):
    module = types.ModuleType("config")
    module.settings = settings_ns
    module.get_settings = lambda: settings_ns
    return module


# Config resolution (pure, the anti-silent-egress rules)


class TestResolveEmbeddingConfig(unittest.TestCase):
    def test_openai_with_key(self):
        cfg = resolve_embedding_config(
            provider="openai", model="text-embedding-3-small", openai_api_key="sk-x"
        )
        self.assertEqual(cfg.provider, "openai")
        self.assertEqual(cfg.api_key, "sk-x")
        self.assertIsNone(cfg.base_url)

    def test_unconfigured_raises_operator_readable_error(self):
        with self.assertRaises(EmbeddingConfigError) as ctx:
            resolve_embedding_config(provider="openai", model="text-embedding-3-small")
        message = str(ctx.exception)
        # The error must tell the operator exactly what to set
        self.assertIn("EMBEDDING_API_KEY", message)
        self.assertIn("OPENAI_API_KEY", message)
        self.assertIn("EMBEDDING_BASE_URL", message)

    def test_local_endpoint_without_key_is_valid(self):
        cfg = resolve_embedding_config(
            provider="openai", model="bge-m3", base_url="http://vllm.internal:8000/v1"
        )
        self.assertEqual(cfg.base_url, "http://vllm.internal:8000/v1")
        self.assertIsNone(cfg.api_key)

    def test_llm_settings_are_inherited_so_all_local_stays_local(self):
        cfg = resolve_embedding_config(
            provider="openai",
            model="bge-m3",
            openai_api_key="sk-llm",
            openai_base_url="http://vllm.internal:8000/v1",
        )
        self.assertEqual(cfg.base_url, "http://vllm.internal:8000/v1")
        self.assertEqual(cfg.api_key, "sk-llm")

    def test_embedding_specific_settings_win_over_llm_settings(self):
        cfg = resolve_embedding_config(
            provider="openai",
            model="bge-m3",
            api_key="sk-embed",
            base_url="http://tei.internal:8080/v1",
            openai_api_key="sk-llm",
            openai_base_url="http://vllm.internal:8000/v1",
        )
        self.assertEqual(cfg.api_key, "sk-embed")
        self.assertEqual(cfg.base_url, "http://tei.internal:8080/v1")

    def test_gemini_uses_google_key_and_compatible_endpoint(self):
        cfg = resolve_embedding_config(
            provider="gemini", model="gemini-embedding-001", google_api_key="g-key"
        )
        self.assertEqual(cfg.provider, "gemini")
        self.assertEqual(cfg.api_key, "g-key")
        self.assertEqual(cfg.base_url, GEMINI_OPENAI_BASE_URL)

    def test_gemini_without_key_raises(self):
        with self.assertRaises(EmbeddingConfigError) as ctx:
            resolve_embedding_config(provider="gemini", model="gemini-embedding-001")
        self.assertIn("GOOGLE_API_KEY", str(ctx.exception))

    def test_unknown_provider_raises_instead_of_openai_fallback(self):
        # The LLM factory warns and falls back to openai; embeddings must
        # NOT: a typo would silently ship documents to a third party.
        with self.assertRaises(EmbeddingConfigError) as ctx:
            resolve_embedding_config(
                provider="cohere", model="embed-v3", openai_api_key="sk-x"
            )
        self.assertIn("cohere", str(ctx.exception))

    def test_dimensions_pass_through(self):
        cfg = resolve_embedding_config(
            provider="openai",
            model="text-embedding-3-large",
            openai_api_key="sk-x",
            dimensions=1024,
        )
        self.assertEqual(cfg.dimensions, 1024)


# Dimension derivation (replaces the 1536 constant)


class TestDimensionResolution(unittest.TestCase):
    def test_declared_dimensions_win_without_probing(self):
        embedder = MockEmbedder(model="anything", dim=512, dimensions=512)
        self.assertEqual(embedder.dimension, 512)
        self.assertEqual(embedder.calls, [])

    def test_known_model_uses_table_without_probing(self):
        embedder = MockEmbedder(model="text-embedding-3-small", dim=1536)
        self.assertEqual(embedder.dimension_if_known(), 1536)
        self.assertEqual(embedder.dimension, 1536)
        self.assertEqual(embedder.calls, [])

    def test_unknown_model_probes_once_and_caches(self):
        embedder = MockEmbedder(model="bge-m3", dim=1024)
        self.assertIsNone(embedder.dimension_if_known())
        self.assertEqual(embedder.dimension, 1024)
        self.assertEqual(embedder.dimension, 1024)
        self.assertEqual(len(embedder.calls), 1)
        self.assertEqual(embedder.dimension_if_known(), 1024)

    def test_failed_probe_becomes_readable_config_error(self):
        class BrokenEmbedder(EmbeddingClient):
            model = "mystery-model"

            def embed(self, texts):
                raise RuntimeError("connection refused")

        with self.assertRaises(EmbeddingConfigError) as ctx:
            _ = BrokenEmbedder().dimension
        message = str(ctx.exception)
        self.assertIn("mystery-model", message)
        self.assertIn("EMBEDDING_DIMENSIONS", message)


# OpenAI-compatible client (fake SDK)


class TestOpenAIEmbeddingClient(unittest.TestCase):
    def _client(self, **kwargs):
        from llm.embeddings import OpenAIEmbeddingClient

        return OpenAIEmbeddingClient(**kwargs)

    def test_embed_returns_vectors_in_input_order(self):
        with mock.patch.dict(sys.modules, {"openai": fake_openai_module()}):
            client = self._client(model="text-embedding-3-small", api_key="sk-x")
            vectors = client.embed(["a", "b", "c"])
        # The fake returns data reversed; sorting by index must restore order
        self.assertEqual([v[0] for v in vectors], [0.0, 1.0, 2.0])

    def test_keyless_local_endpoint_gets_placeholder_key(self):
        # The openai SDK refuses api_key=None; local endpoints need no key
        with mock.patch.dict(sys.modules, {"openai": fake_openai_module()}):
            self._client(model="bge-m3", base_url="http://vllm.internal:8000/v1")
            self.assertTrue(FakeOpenAI.last_instance.api_key)
            self.assertEqual(
                FakeOpenAI.last_instance.base_url, "http://vllm.internal:8000/v1"
            )

    def test_dimensions_param_only_sent_to_real_openai(self):
        with mock.patch.dict(sys.modules, {"openai": fake_openai_module()}):
            client = self._client(
                model="text-embedding-3-large", api_key="sk-x", dimensions=1024
            )
            client.embed(["a"])
            self.assertEqual(
                FakeOpenAI.last_instance.embeddings.calls[0].get("dimensions"), 1024
            )
            client = self._client(
                model="bge-m3",
                base_url="http://vllm.internal:8000/v1",
                dimensions=1024,
            )
            client.embed(["a"])
            self.assertNotIn(
                "dimensions", FakeOpenAI.last_instance.embeddings.calls[0]
            )

    def test_empty_input_makes_no_api_call(self):
        with mock.patch.dict(sys.modules, {"openai": fake_openai_module()}):
            client = self._client(model="text-embedding-3-small", api_key="sk-x")
            self.assertEqual(client.embed([]), [])
            self.assertEqual(FakeOpenAI.last_instance.embeddings.calls, [])


class TestCreateEmbeddingClientFactory(unittest.TestCase):
    def setUp(self):
        create_embedding_client.cache_clear()
        self.addCleanup(create_embedding_client.cache_clear)

    def test_unconfigured_settings_raise_readable_error(self):
        modules = {"config": fake_config_module(fake_settings())}
        with mock.patch.dict(sys.modules, modules):
            with self.assertRaises(EmbeddingConfigError):
                create_embedding_client()

    def test_local_endpoint_builds_openai_compatible_client(self):
        settings_ns = fake_settings(
            embedding_model="bge-m3",
            embedding_base_url="http://vllm.internal:8000/v1",
        )
        modules = {
            "config": fake_config_module(settings_ns),
            "openai": fake_openai_module(),
        }
        with mock.patch.dict(sys.modules, modules):
            client = create_embedding_client()
            self.assertEqual(client.model, "bge-m3")
            self.assertEqual(
                FakeOpenAI.last_instance.base_url, "http://vllm.internal:8000/v1"
            )


# Root-cause sweep: no hardwired OpenAI embedding path can exist


class TestNoHardwiredOpenAIEmbedding(unittest.TestCase):
    def _backend_sources(self):
        for path in BACKEND_ROOT.rglob("*.py"):
            parts = set(path.parts)
            if parts & {"venv", "tests", "__pycache__"}:
                continue
            yield path

    def test_no_llama_index_openai_embedding_anywhere(self):
        pattern = re.compile(r"\bOpenAIEmbedding\b|llama_index\.embeddings")
        offenders = [
            str(path)
            for path in self._backend_sources()
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_vector_size_constant_removed_from_settings(self):
        source = (BACKEND_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertNotIn("qdrant_vector_size", source)
        self.assertNotIn("1536", source)


# Vector store: dimension follows the model, mismatch is loud


class FakeQdrantServer:
    """Collection registry: {name: vector_size}."""

    def __init__(self):
        self.collections = {}
        self.upserts = []
        self.searches = []


class _FakeCollectionsList:
    def __init__(self, names):
        self.collections = [SimpleNamespace(name=n) for n in names]


def _collection_info(size):
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=size))
        ),
        points_count=0,
        vectors_count=0,
        indexed_vectors_count=0,
        status="green",
    )


def fake_qdrant_modules(server):
    class FakeQdrantClient:
        def __init__(self, host=None, port=None):
            self._server = server

        def get_collections(self):
            return _FakeCollectionsList(list(self._server.collections))

        def get_collection(self, name):
            return _collection_info(self._server.collections[name])

        def create_collection(self, collection_name, vectors_config):
            self._server.collections[collection_name] = vectors_config.size

        def create_payload_index(self, **kwargs):
            return None

        def upsert(self, collection_name, points):
            self._server.upserts.append((collection_name, points))

        def delete(self, **kwargs):
            return None

        def scroll(self, **kwargs):
            return [], None

        def count(self, **kwargs):
            return SimpleNamespace(count=0)

    class FakeAsyncQdrantClient:
        def __init__(self, host=None, port=None):
            self._server = server

        async def query_points(self, **kwargs):
            self._server.searches.append(kwargs)
            return SimpleNamespace(points=[])

    class _Model:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    qdrant_client = types.ModuleType("qdrant_client")
    qdrant_client.QdrantClient = FakeQdrantClient
    qdrant_client.AsyncQdrantClient = FakeAsyncQdrantClient

    http_mod = types.ModuleType("qdrant_client.http")
    models_mod = types.ModuleType("qdrant_client.http.models")
    for name in (
        "VectorParams", "Filter", "FieldCondition", "MatchValue", "MatchAny",
        "IsEmptyCondition", "PayloadField", "PointStruct", "FilterSelector",
    ):
        setattr(models_mod, name, type(name, (_Model,), {}))
    models_mod.Distance = SimpleNamespace(COSINE="Cosine")
    models_mod.PayloadSchemaType = SimpleNamespace(KEYWORD="keyword")
    http_mod.models = models_mod
    qdrant_client.http = http_mod

    return {
        "qdrant_client": qdrant_client,
        "qdrant_client.http": http_mod,
        "qdrant_client.http.models": models_mod,
    }


def fake_llama_index_modules():
    core = types.ModuleType("llama_index.core")

    class Document:
        def __init__(self, text="", metadata=None):
            self.text = text
            self.metadata = metadata or {}

    class SimpleDirectoryReader:
        def __init__(self, **kwargs):
            pass

        def load_data(self):
            return []

    class _Splitter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_nodes_from_documents(self, docs):
            return []

    node_parser = types.ModuleType("llama_index.core.node_parser")
    node_parser.SemanticSplitterNodeParser = type(
        "SemanticSplitterNodeParser", (_Splitter,), {}
    )
    node_parser.SentenceSplitter = type("SentenceSplitter", (_Splitter,), {})

    embeddings_mod = types.ModuleType("llama_index.core.embeddings")

    class BaseEmbedding:
        def __init__(self, **kwargs):
            pass

    embeddings_mod.BaseEmbedding = BaseEmbedding

    core.Document = Document
    core.SimpleDirectoryReader = SimpleDirectoryReader
    root = types.ModuleType("llama_index")
    root.core = core

    return {
        "llama_index": root,
        "llama_index.core": core,
        "llama_index.core.node_parser": node_parser,
        "llama_index.core.embeddings": embeddings_mod,
    }


class VectorStoreTestCase(unittest.TestCase):
    """Loads rag.vector_store fresh under fake qdrant/llama_index/config."""

    def load(self, server, settings_ns):
        modules = {
            **fake_qdrant_modules(server),
            **fake_llama_index_modules(),
            "config": fake_config_module(settings_ns),
        }
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [n for n in list(sys.modules) if n == "rag" or n.startswith("rag.")]:
            del sys.modules[name]
        module = importlib.import_module("rag.vector_store")
        module.clear_cache()  # search results are cached in-process
        self.addCleanup(module.clear_cache)
        return module


class TestVectorStoreDimensions(VectorStoreTestCase):
    def test_collection_created_with_model_dimension_not_1536(self):
        server = FakeQdrantServer()
        module = self.load(server, fake_settings())
        embedder = MockEmbedder(model="bge-m3", dim=1024)
        module.QdrantVectorStore(embedder=embedder)
        self.assertEqual(server.collections["test_collection"], 1024)

    def test_existing_collection_with_known_mismatch_fails_at_init(self):
        server = FakeQdrantServer()
        server.collections["test_collection"] = 1536  # created with OpenAI dims
        module = self.load(server, fake_settings())
        embedder = MockEmbedder(model="anything", dim=768, dimensions=768)
        with self.assertRaises(EmbeddingConfigError) as ctx:
            module.QdrantVectorStore(embedder=embedder)
        message = str(ctx.exception)
        self.assertIn("1536", message)
        self.assertIn("768", message)
        self.assertIn("test_collection", message)

    def test_existing_collection_with_matching_dimension_is_fine(self):
        server = FakeQdrantServer()
        server.collections["test_collection"] = 768
        module = self.load(server, fake_settings())
        store = module.QdrantVectorStore(embedder=MockEmbedder(dim=768, dimensions=768))
        self.assertIsNotNone(store)

    def test_unknown_model_mismatch_fails_at_search_not_silently(self):
        server = FakeQdrantServer()
        server.collections["test_collection"] = 1536
        module = self.load(server, fake_settings())
        store = module.QdrantVectorStore(embedder=MockEmbedder(model="bge-m3", dim=768))
        with self.assertRaises(EmbeddingConfigError):
            run(store.search_async(query="anything"))
        self.assertEqual(server.searches, [])  # never reached Qdrant

    def test_unknown_model_mismatch_fails_at_index_not_skipped(self):
        server = FakeQdrantServer()
        server.collections["test_collection"] = 1536
        module = self.load(server, fake_settings())
        store = module.QdrantVectorStore(embedder=MockEmbedder(model="bge-m3", dim=768))
        chunk = module.SemanticChunk(
            content="hello", metadata={}, chunk_id="c1", source_document="doc"
        )
        with self.assertRaises(EmbeddingConfigError):
            store.index_chunks([chunk])
        self.assertEqual(server.upserts, [])

    def test_search_uses_the_injected_embedder(self):
        server = FakeQdrantServer()
        module = self.load(server, fake_settings())
        embedder = MockEmbedder(model="bge-m3", dim=64)
        store = module.QdrantVectorStore(embedder=embedder)
        run(store.search_async(query="local search"))
        self.assertGreater(len(embedder.calls), 0)
        self.assertEqual(len(server.searches), 1)


class TestChunkerEmbeddingConfig(VectorStoreTestCase):
    def test_chunker_with_unconfigured_embedding_raises_readable(self):
        create_embedding_client.cache_clear()
        self.addCleanup(create_embedding_client.cache_clear)
        server = FakeQdrantServer()
        module_settings = fake_settings()  # no key, no base_url
        self.load(server, module_settings)
        chunker_module = importlib.import_module("rag.chunker")
        with self.assertRaises(EmbeddingConfigError):
            chunker_module.SemanticChunker()

    def test_chunker_accepts_injected_embedder(self):
        server = FakeQdrantServer()
        self.load(server, fake_settings())
        chunker_module = importlib.import_module("rag.chunker")
        chunker = chunker_module.SemanticChunker(embed_model=MockEmbedder(dim=16))
        self.assertIsNotNone(chunker)


# Real llama_index integration (venv only)


def _llama_index_available():
    try:
        import llama_index.core
        return True
    except Exception:
        return False


@unittest.skipUnless(_llama_index_available(), "llama_index not installed")
class TestRealLlamaIndexAdapter(unittest.TestCase):
    def test_semantic_splitter_accepts_wrapped_embedder(self):
        # Guards the adapter against the real BaseEmbedding
        from rag.chunker import SemanticChunker

        embedder = MockEmbedder(model="bge-m3", dim=8)
        chunker = SemanticChunker(embed_model=embedder)
        chunks = chunker.chunk_text(
            "The sky is blue today. Clouds drift slowly. "
            "Databases store rows. Indexes speed up queries.",
            source_name="test-doc",
        )
        self.assertGreater(len(chunks), 0)
        self.assertGreater(len(embedder.calls), 0)


def _config_available():
    try:
        import config  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_config_available(), "config (pydantic_settings) not installed")
class TestRealSettings(unittest.TestCase):
    def test_qdrant_vector_size_setting_is_gone(self):
        from config import settings

        self.assertFalse(hasattr(settings, "qdrant_vector_size"))


if __name__ == "__main__":
    unittest.main()
