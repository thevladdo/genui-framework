"""
OpenAI chat client (and OpenAI-compatible providers).

Covers more than OpenAI itself: any endpoint speaking the OpenAI chat
API works via `base_url`: Google Gemini (OpenAI-compatible endpoint),
Azure OpenAI, Mistral, vLLM, Ollama, OpenRouter, ...
"""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from utils.tracing import span

from .base import LLMChatClient, ToolHandler, ToolSpec

logger = logging.getLogger(__name__)


class OpenAIChatClient(LLMChatClient):
    """LLMChatClient over the OpenAI (compatible) chat completions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        provider_name: str = "openai",
        timeout: Optional[float] = None,
    ):
        # Imported lazily so the module can be imported and tested without the SDK installed
        from openai import AsyncOpenAI

        self.model = model
        self.provider_name = provider_name
        client_kwargs: Dict[str, Any] = {"api_key": api_key, "base_url": base_url}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._client = AsyncOpenAI(**client_kwargs)
        # Downgraded at runtime if the endpoint rejects json_schema
        self._supports_json_schema = True

    async def complete_json(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        with span(
            "genui.llm.complete",
            provider=self.provider_name,
            model=self.model,
        ):
            if json_schema is not None and self._supports_json_schema:
                try:
                    response = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "genui_output", "schema": json_schema},
                        },
                    )
                    return response.choices[0].message.content or ""
                except Exception as e:
                    logger.warning(
                        "json_schema response_format rejected by %s (%s); "
                        "falling back to json_object", self.provider_name, e
                    )
                    self._supports_json_schema = False

            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""

    async def complete_json_with_tools(
        self,
        system: str,
        user: str,
        tools: List[ToolSpec],
        tool_handler: ToolHandler,
        max_tool_rounds: int = 3,
    ) -> str:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

        with span(
            "genui.llm.complete_tools",
            provider=self.provider_name,
            model=self.model,
        ):
            for _ in range(max_tool_rounds):
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tools,
                    response_format={"type": "json_object"},
                )
                message = response.choices[0].message
                if not message.tool_calls:
                    return message.content or ""

                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                })
                for tc in message.tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    try:
                        result = await tool_handler(tc.function.name, arguments)
                    except Exception as e:
                        logger.warning("Tool %s failed: %s", tc.function.name, e)
                        result = f"tool error: {e}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

            # Tool budget exhausted -> force a final answer without tools
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""

    async def stream_json(
        self,
        system: str,
        user: str,
    ) -> AsyncIterator[str]:
        with span(
            "genui.llm.stream",
            provider=self.provider_name,
            model=self.model,
        ):
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
