"""
LLM provider abstraction.

The ZoneAgent (and anything else that needs JSON-constrained chat
completions) talks to an LLMChatClient, never to a provider SDK
directly. Provider selection is configuration (LLM_PROVIDER), not code.

Embeddings follow the same rule: the RAG pipeline talks to an
EmbeddingClient (EMBEDDING_PROVIDER / EMBEDDING_BASE_URL), never to a
hardwired provider.
"""

from .base import LLMChatClient
from .embeddings import (
    EmbeddingClient,
    EmbeddingConfigError,
    create_embedding_client,
    resolve_embedding_config,
)
from .factory import GEMINI_OPENAI_BASE_URL, create_llm_client, resolve_provider_config

__all__ = [
    "GEMINI_OPENAI_BASE_URL",
    "EmbeddingClient",
    "EmbeddingConfigError",
    "LLMChatClient",
    "create_embedding_client",
    "create_llm_client",
    "resolve_embedding_config",
    "resolve_provider_config",
]
