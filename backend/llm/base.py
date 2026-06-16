"""
LLM Chat Client Interface
Minimal async surface the framework needs from any LLM provider:
JSON-constrained completion and raw-delta streaming.

The server-side guarantees (Pydantic/jsonschema validation, URL
whitelist, pinned enforcement) do NOT depend on the provider honoring
the schema — provider-native structured output is an optimization, the
validation pipeline is the guarantee. This keeps the interface small
enough that adding a provider is one file.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Optional


class LLMChatClient(ABC):
    """Async chat-completion client constrained to JSON output."""

    @abstractmethod
    async def complete_json(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Run a completion that must return a JSON document.

        Args:
            system: System prompt.
            user: User prompt.
            json_schema: Optional schema for provider-native structured
                output. Providers without schema support may ignore it
                (the prompt already specifies the structure, and output
                is validated server-side regardless).

        Returns:
            The raw response text (expected to be JSON).
        """

    @abstractmethod
    def stream_json(
        self,
        system: str,
        user: str,
    ) -> AsyncIterator[str]:
        """
        Stream a JSON completion as raw text deltas.

        Yields:
            Text fragments in generation order; concatenated they form
            the full JSON document.
        """
