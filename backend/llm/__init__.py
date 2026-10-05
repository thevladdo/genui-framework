"""
LLM provider abstraction.

Agents (and anything else that needs JSON-constrained chat completions) talk to an LLMChatClient made for their role, never to a provider SDK directly.
Which provider and model serve a role is configuration (llm.routing), not code.

Embeddings follow the same rule: the RAG pipeline talks to an EmbeddingClient (EMBEDDING_PROVIDER / EMBEDDING_BASE_URL), never to a hardwired provider.
"""

from .base import LLMChatClient
from .embeddings import (
    EmbeddingClient,
    EmbeddingConfigError,
    create_embedding_client,
    resolve_embedding_config,
)
from .factory import answered_model, create_llm_client
from .routing import GEMINI_OPENAI_BASE_URL, LLMConfigError, Role, resolve_provider_config

__all__ = [
    "GEMINI_OPENAI_BASE_URL",
    "EmbeddingClient",
    "EmbeddingConfigError",
    "LLMChatClient",
    "LLMConfigError",
    "Role",
    "answered_model",
    "create_embedding_client",
    "create_llm_client",
    "resolve_embedding_config",
    "resolve_provider_config",
]
