"""
LLM provider abstraction.

The ZoneAgent (and anything else that needs JSON-constrained chat
completions) talks to an LLMChatClient, never to a provider SDK
directly. Provider selection is configuration (LLM_PROVIDER), not code.
"""

from .base import LLMChatClient
from .factory import GEMINI_OPENAI_BASE_URL, create_llm_client, resolve_provider_config

__all__ = [
    "GEMINI_OPENAI_BASE_URL",
    "LLMChatClient",
    "create_llm_client",
    "resolve_provider_config",
]
