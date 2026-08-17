"""
Anthropic chat client.

Anthropic has no JSON response_format; JSON is enforced by the prompt
plus a pre-filled "{" assistant turn (forces the reply to start as a
JSON object). The server-side validation pipeline remains the actual
guarantee, exactly as with every other provider.

Requires the optional `anthropic` package (see requirements.txt).
"""

import logging
from typing import Any, AsyncIterator, Dict, Optional

from utils.tracing import span

from .base import LLMChatClient

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 4096


class AnthropicChatClient(LLMChatClient):
    """LLMChatClient over the Anthropic Messages API."""

    prompt_cache = "explicit"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        timeout: Optional[float] = None,
    ):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise ImportError(
                "LLM_PROVIDER=anthropic requires the 'anthropic' package: "
                "pip install anthropic"
            ) from e

        self.model = model
        self.max_tokens = max_tokens
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._client = AsyncAnthropic(**client_kwargs)

    @staticmethod
    def _json_messages(user: str) -> list:
        return [
            {"role": "user", "content": user},
            # Pre-fill: the model continues from "{", so the response is
            # forced to start as a JSON object
            {"role": "assistant", "content": "{"},
        ]

    @staticmethod
    def _json_text(response) -> str:
        """The reply, with the pre-filled brace put back in front."""
        return "{" + "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        )

    async def complete_json(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        with span("genui.llm.complete", provider="anthropic", model=self.model):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=self._json_messages(user),
            )
            return self._json_text(response)

    async def complete_json_cached(
        self,
        system: str,
        cached_prefix: str,
        user: str,
    ) -> str:
        """
        The repeated prefix as its own system block, with a cache
        breakpoint on it: written once for the batch, read back for every
        call after the first. Below the provider's minimum block size the
        marker is ignored and the call behaves like an uncached one.
        """
        with span("genui.llm.complete_cached", provider="anthropic", model=self.model):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {"type": "text", "text": system},
                    {
                        "type": "text",
                        "text": cached_prefix,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                messages=self._json_messages(user),
            )
            return self._json_text(response)

    async def stream_json(
        self,
        system: str,
        user: str,
    ) -> AsyncIterator[str]:
        with span("genui.llm.stream", provider="anthropic", model=self.model):
            # The pre-filled "{" must reach the downstream JSON parser too
            yield "{"

            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=self._json_messages(user),
            ) as stream:
                async for delta in stream.text_stream:
                    if delta:
                        yield delta
