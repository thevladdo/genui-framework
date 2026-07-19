"""
Embedding provider abstraction (BYOK, like the chat client).

The RAG pipeline (chunker, vector store) talks to an EmbeddingClient,
never to a provider SDK directly. Provider selection is configuration
(EMBEDDING_PROVIDER), not code, and an OpenAI-compatible base_url covers
vLLM / Ollama / TEI / RunPod / Azure — so "everything runs in-house"
means embeddings too, not just generation.

Two rules with no exceptions:
- an unconfigured embedding raises an operator-readable error; there is
  NO silent fallback to api.openai.com (documents must never leave the
  operator's infrastructure unannounced);
- the vector dimension derives from the model (known table, explicit
  EMBEDDING_DIMENSIONS, or a one-time probe), never from a constant.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional

from utils.tracing import span

from .factory import GEMINI_OPENAI_BASE_URL

logger = logging.getLogger(__name__)

# Native output dimensions of well-known models: lets the vector store validate an existing collection without a network round-trip.
_KNOWN_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "gemini-embedding-001": 3072,
}


class EmbeddingConfigError(RuntimeError):
    """Embedding misconfiguration: fail loudly, never degrade silently."""


class EmbeddingClient(ABC):
    """Sync embedding client: embed(texts) -> vectors."""

    model: str
    declared_dimensions: Optional[int] = None
    _probed_dimension: Optional[int] = None

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts, preserving input order."""

    def dimension_if_known(self) -> Optional[int]:
        """Vector size without network I/O; None if only a probe can tell."""
        if self.declared_dimensions:
            return self.declared_dimensions
        return _KNOWN_DIMENSIONS.get(self.model) or self._probed_dimension

    @property
    def dimension(self) -> int:
        """Vector size of this model; probes once (and caches) if unknown."""
        known = self.dimension_if_known()
        if known:
            return known
        try:
            self._probed_dimension = len(self.embed(["dimension probe"])[0])
        except Exception as e:
            raise EmbeddingConfigError(
                f"Could not determine the vector dimension of embedding model "
                f"'{self.model}' (probe failed: {e}). Set EMBEDDING_DIMENSIONS "
                f"to declare it explicitly, or fix the endpoint configuration."
            ) from e
        return self._probed_dimension


class OpenAIEmbeddingClient(EmbeddingClient):
    """EmbeddingClient over the OpenAI (compatible) embeddings API."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        dimensions: Optional[int] = None,
        provider_name: str = "openai",
        timeout: Optional[float] = None,
    ):
        # Imported lazily so the module can be imported and tested without the SDK installed
        from openai import OpenAI

        self.model = model
        self.declared_dimensions = dimensions
        self.provider_name = provider_name
        self._base_url = base_url
        client_kwargs = {"api_key": api_key or "sk-no-key-required", "base_url": base_url}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._client = OpenAI(**client_kwargs)

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        kwargs = {}
        if self.declared_dimensions and self._base_url is None:
            kwargs["dimensions"] = self.declared_dimensions
        with span(
            "genui.embedding",
            provider=self.provider_name,
            model=self.model,
            batch_size=len(texts),
        ):
            response = self._client.embeddings.create(
                model=self.model, input=list(texts), **kwargs
            )
        data = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in data]


@dataclass(frozen=True)
class EmbeddingProviderConfig:
    """Resolved embedding configuration (pure, testable)."""
    provider: str  # "openai" | "gemini"
    model: str
    api_key: Optional[str]
    base_url: Optional[str]
    dimensions: Optional[int]


def resolve_embedding_config(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    dimensions: Optional[int] = None,
    openai_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> EmbeddingProviderConfig:
    """
    Map settings to a concrete embedding configuration.

    Embedding-specific settings win; otherwise the LLM's OpenAI settings
    are inherited, so an operator who pointed the LLM at an in-house
    endpoint gets in-house embeddings too. Unlike the LLM factory, an
    unknown provider is an error, not a fallback: falling back would
    silently ship documents to a third party.
    """
    normalized = (provider or "openai").strip().lower()

    if normalized in ("gemini", "google"):
        key = api_key or google_api_key
        if not key:
            raise EmbeddingConfigError(
                "EMBEDDING_PROVIDER=gemini requires GOOGLE_API_KEY (or "
                "EMBEDDING_API_KEY). Embeddings never fall back to another "
                "provider."
            )
        return EmbeddingProviderConfig(
            "gemini", model, key, base_url or GEMINI_OPENAI_BASE_URL, dimensions
        )

    if normalized != "openai":
        raise EmbeddingConfigError(
            f"Unknown EMBEDDING_PROVIDER '{provider}'. Supported: 'openai' "
            f"(covers any OpenAI-compatible endpoint via EMBEDDING_BASE_URL: "
            f"vLLM, Ollama, TEI, RunPod, Azure) and 'gemini'. Embeddings "
            f"never fall back to another provider: your documents would "
            f"silently leave your infrastructure."
        )

    if not model:
        raise EmbeddingConfigError("EMBEDDING_MODEL is not set.")

    key = api_key or openai_api_key
    url = base_url or openai_base_url
    if not key and not url:
        raise EmbeddingConfigError(
            "Embedding is not configured: documents cannot be indexed or "
            "searched. Set EMBEDDING_API_KEY (or OPENAI_API_KEY) to use "
            "OpenAI, or EMBEDDING_BASE_URL to an OpenAI-compatible endpoint "
            "(vLLM, Ollama, TEI, RunPod) to keep embeddings inside your own "
            f"infrastructure. Configured embedding model: '{model}'."
        )
    return EmbeddingProviderConfig("openai", model, key, url, dimensions)


# One client per process: embedding clients are stateless and the dimension probe (when needed) must run once.
@lru_cache(maxsize=None)
def create_embedding_client() -> EmbeddingClient:
    """Create the configured embedding client."""
    from config import settings

    config = resolve_embedding_config(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions,
        openai_api_key=settings.openai_api_key,
        google_api_key=settings.google_api_key,
        openai_base_url=settings.openai_base_url,
    )
    return OpenAIEmbeddingClient(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        dimensions=config.dimensions,
        provider_name=config.provider,
        timeout=settings.llm_timeout_seconds,
    )
