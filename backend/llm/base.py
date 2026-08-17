"""
LLM Chat Client Interface
Minimal async surface the framework needs from any LLM provider:
JSON-constrained completion and raw-delta streaming.

The server-side guarantees (Pydantic/jsonschema validation, URL
whitelist, pinned enforcement) do NOT depend on the provider honoring
the schema. Provider-native structured output is an optimization, the
validation pipeline is the guarantee. This keeps the interface small
enough that adding a provider is one file.
"""

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, AsyncIterator, Dict, List, Optional

# Provider-neutral tool spec: {"name", "description", "parameters": <json schema>}
ToolSpec = Dict[str, Any]
# Async callback the client invokes when the model calls a tool:
# (tool_name, arguments) -> tool result as text
ToolHandler = Callable[[str, Dict[str, Any]], Awaitable[str]]


class LLMChatClient(ABC):
    """Async chat-completion client constrained to JSON output."""

    # How this client reuses a repeated prompt prefix:
    #   "explicit"  the client marks the prefix and the provider bills it once
    #   "prefix"    the prefix is sent first and identical every time, so an endpoint that caches prefixes on its own reuses it 
    prompt_cache = "prefix"

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

    async def complete_json_cached(
        self,
        system: str,
        cached_prefix: str,
        user: str,
    ) -> str:
        """
        Like complete_json, with `cached_prefix` declared as the part that
        repeats identically across a batch of calls.

        Used where one long text is the context of many small questions
        about it. Paying for that text once instead of once per question
        is the difference between a technique being affordable and being
        an order of magnitude more expensive.

        Default: fold the prefix into the system prompt, first and
        unchanged. Correct on every provider, and an endpoint that caches
        prompt prefixes by itself (OpenAI, vLLM) still bills the repeat
        once. A provider that caches nothing pays it every time: more
        expensive, never broken.
        """
        return await self.complete_json(f"{system}\n\n{cached_prefix}", user)

    async def complete_json_with_tools(
        self,
        system: str,
        user: str,
        tools: List[ToolSpec],
        tool_handler: ToolHandler,
        max_tool_rounds: int = 3,
    ) -> str:
        """
        Like complete_json, but the model may call the given tools; the
        client runs the tool loop and returns the final JSON text.

        Default: providers without a tool loop ignore the tools and
        answer from the prompt alone (callers always pre-fetch context
        into the prompt, so this degrades quality, not correctness).
        """
        return await self.complete_json(system, user)

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
