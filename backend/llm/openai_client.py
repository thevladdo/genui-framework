"""
OpenAI clients.

OpenAIResponsesClient calls OpenAI's own endpoint through the Responses API (/v1/responses).
OpenAIChatClient calls chat completions, which is what the OpenAI-compatible endpoints reached through `base_url` speak: Google Gemini, Azure OpenAI, Mistral, vLLM, Ollama, OpenRouter, ...
"""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from utils.tracing import span

from .base import LLMChatClient, ToolHandler, ToolSpec

logger = logging.getLogger(__name__)


def _format_rejected(error: Exception) -> bool:
    """A 400 to a structured-output request is the endpoint refusing the schema; anything else is a failed call."""
    return getattr(error, "status_code", None) == 400


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
                    if not _format_rejected(e):
                        raise
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
                    except Exception:
                        logger.warning("Tool %s failed", tc.function.name, exc_info=True)
                        result = f"tool error: {tc.function.name} failed"
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


class OpenAIResponsesClient(OpenAIChatClient):
    """
    Reasoning models take function tools only here: chat completions refuse tools while reasoning is on.
    With store=False OpenAI keeps no response, so the tool loop resends its own items, reasoning included.
    """

    async def _create(self, system: str, items: Any, text_format: Dict[str, Any], **kwargs) -> Any:
        # Not `instructions`: json_object requires the word "json" in the input messages, and only the system prompts carry it
        if isinstance(items, str):
            items = [{"role": "user", "content": items}]
        return await self._client.responses.create(
            model=self.model,
            input=[{"role": "developer", "content": system}, *items],
            text={"format": text_format},
            store=False,
            **kwargs,
        )

    async def complete_json(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        with span("genui.llm.complete", provider=self.provider_name, model=self.model):
            if json_schema is not None and self._supports_json_schema:
                try:
                    response = await self._create(
                        system,
                        user,
                        {"type": "json_schema", "name": "genui_output", "schema": json_schema, "strict": False},
                    )
                    return response.output_text
                except Exception as e:
                    if not _format_rejected(e):
                        raise
                    logger.warning("json_schema format rejected by %s (%s); falling back to json_object", self.provider_name, e)
                    self._supports_json_schema = False

            return (await self._create(system, user, {"type": "json_object"})).output_text

    async def complete_json_with_tools(
        self,
        system: str,
        user: str,
        tools: List[ToolSpec],
        tool_handler: ToolHandler,
        max_tool_rounds: int = 3,
    ) -> str:
        items: List[Dict[str, Any]] = [{"role": "user", "content": user}]
        # Strict is the default here and needs every property required
        function_tools = [
            {
                "type": "function",
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                "strict": False,
            }
            for t in tools
        ]
        json_format = {"type": "json_object"}

        with span("genui.llm.complete_tools", provider=self.provider_name, model=self.model):
            for _ in range(max_tool_rounds):
                response = await self._create(
                    system, items, json_format, tools=function_tools, include=["reasoning.encrypted_content"]
                )
                calls = [item for item in response.output if item.type == "function_call"]
                if not calls:
                    return response.output_text

                items += [item.model_dump(exclude_none=True) for item in response.output]
                for call in calls:
                    try:
                        arguments = json.loads(call.arguments or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    try:
                        result = await tool_handler(call.name, arguments)
                    except Exception:
                        logger.warning("Tool %s failed", call.name, exc_info=True)
                        result = f"tool error: {call.name} failed"
                    items.append({"type": "function_call_output", "call_id": call.call_id, "output": result})

            response = await self._create(
                system, items, json_format, tools=function_tools, tool_choice="none", include=["reasoning.encrypted_content"]
            )
            return response.output_text

    async def stream_json(
        self,
        system: str,
        user: str,
    ) -> AsyncIterator[str]:
        with span("genui.llm.stream", provider=self.provider_name, model=self.model):
            stream = await self._create(system, user, {"type": "json_object"}, stream=True)
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield event.delta
                elif event.type in ("response.failed", "response.incomplete", "error"):
                    raise RuntimeError(f"{self.provider_name} stream ended with {event.type}: {_stream_problem(event)}")


def _stream_problem(event: Any) -> str:
    response = getattr(event, "response", None)
    error = getattr(response, "error", None) or event
    details = getattr(response, "incomplete_details", None)
    return getattr(error, "message", None) or getattr(details, "reason", None) or "no detail"
