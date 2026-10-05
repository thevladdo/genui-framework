"""
LLM client factory: every client is made for a role, and the role's route (llm.routing) decides provider and model.

    openai     -> OpenAI (or any OpenAI-compatible endpoint via OPENAI_BASE_URL)
    anthropic  -> Anthropic Messages API
    gemini     -> Google Gemini through its OpenAI-compatible endpoint (no extra dependency)
"""

import logging
import time
from contextvars import ContextVar
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from .base import LLMChatClient, ToolHandler, ToolSpec
from .routing import (
    GEMINI_OPENAI_BASE_URL,
    LLMConfigError,
    ProviderConfig,
    Role,
    Route,
    Target,
    provider_configured,
    resolve_provider_config,
    resolve_route,
    route_problems,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GEMINI_OPENAI_BASE_URL",
    "LLMConfigError",
    "ProviderConfig",
    "Role",
    "RoutedChatClient",
    "answered_model",
    "create_llm_client",
    "llm_config_problems",
    "llm_configured",
    "provider_configured",
    "resolve_provider_config",
]

# A context variable: one agent instance serves concurrent requests, and each reads the model of its own call
_answered: ContextVar[Optional[Tuple[Any, str]]] = ContextVar("genui_llm_answered", default=None)

_clients: Dict[Tuple[Any, ...], LLMChatClient] = {}


def answered_model(client: Any) -> Optional[str]:
    answered = _answered.get()
    if answered is not None and answered[0] is client:
        return answered[1]
    return getattr(client, "model", None)


def _metrics():
    from metrics.ops import get_ops_metrics
    return get_ops_metrics()


class RoutedChatClient(LLMChatClient):
    def __init__(self, route: Route, primary: LLMChatClient, fallback: Optional[LLMChatClient] = None):
        self.route = route
        self.role = route.role.value
        self.model = route.primary.model
        self.prompt_cache = primary.prompt_cache
        self._primary = primary
        self._fallback = fallback if route.fallback else None

    def _record(self, target: Target, started: float, outcome: str) -> None:
        _metrics().observe_model_call(
            self.role, target.provider, target.model, time.perf_counter() - started, outcome
        )

    async def _call(self, method: str, *args, **kwargs) -> str:
        started = time.perf_counter()
        try:
            text = await getattr(self._primary, method)(*args, **kwargs)
        except Exception as e:
            self._record(self.route.primary, started, "error")
            if self._fallback is None:
                raise
            return await self._call_fallback(e, method, *args, **kwargs)
        self._record(self.route.primary, started, "ok")
        _answered.set((self, self.route.primary.model))
        return text

    async def _call_fallback(self, cause: Exception, method: str, *args, **kwargs) -> str:
        self._note_fallback(cause)
        started = time.perf_counter()
        try:
            text = await getattr(self._fallback, method)(*args, **kwargs)
        except Exception:
            self._record(self.route.fallback, started, "error")
            raise
        self._record(self.route.fallback, started, "ok")
        _answered.set((self, self.route.fallback.model))
        return text

    def _note_fallback(self, cause: Exception) -> None:
        logger.warning(
            "role %s: %s failed (%s), answering with the declared fallback %s",
            self.role, self.route.primary.model, cause, self.route.fallback.model,
        )
        _metrics().observe_fallback(self.role, self.route.primary.model, self.route.fallback.model)

    async def complete_json(self, system: str, user: str, json_schema: Optional[Dict[str, Any]] = None) -> str:
        return await self._call("complete_json", system, user, json_schema)

    async def complete_json_cached(self, system: str, cached_prefix: str, user: str) -> str:
        return await self._call("complete_json_cached", system, cached_prefix, user)

    async def complete_json_with_tools(
        self,
        system: str,
        user: str,
        tools: List[ToolSpec],
        tool_handler: ToolHandler,
        max_tool_rounds: int = 3,
    ) -> str:
        return await self._call(
            "complete_json_with_tools", system, user, tools, tool_handler, max_tool_rounds
        )

    async def stream_json(self, system: str, user: str) -> AsyncIterator[str]:
        """
        Falls back only before the first delta.
        Once text has reached the caller a second model cannot continue it, so a later failure propagates.
        """
        started = time.perf_counter()
        streamed = False
        try:
            async for delta in self._primary.stream_json(system, user):
                streamed = True
                yield delta
        except Exception as e:
            self._record(self.route.primary, started, "error")
            if self._fallback is None or streamed:
                raise
            self._note_fallback(e)
            started = time.perf_counter()
            try:
                async for delta in self._fallback.stream_json(system, user):
                    yield delta
            except Exception:
                self._record(self.route.fallback, started, "error")
                raise
            self._record(self.route.fallback, started, "ok")
            _answered.set((self, self.route.fallback.model))
            return
        self._record(self.route.primary, started, "ok")
        _answered.set((self, self.route.primary.model))


def _provider_client(target: Target, timeout: Optional[float]) -> LLMChatClient:
    key = (target.provider, target.model, target.base_url, target.api_key, timeout)
    client = _clients.get(key)
    if client is not None:
        return client

    if target.provider == "anthropic":
        from .anthropic_client import AnthropicChatClient
        client = AnthropicChatClient(api_key=target.api_key, model=target.model, timeout=timeout)
    else:
        from .openai_client import OpenAIChatClient, OpenAIResponsesClient
        api = OpenAIResponsesClient if target.provider == "openai" and not target.base_url else OpenAIChatClient
        client = api(
            api_key=target.api_key,
            model=target.model,
            base_url=target.base_url,
            provider_name=target.provider,
            timeout=timeout,
        )
    _clients[key] = client
    return client


def _settings(settings: Any) -> Any:
    if settings is None:
        from config import settings
    return settings


def create_llm_client(role: Role, settings: Any = None) -> RoutedChatClient:
    settings = _settings(settings)
    route = resolve_route(role, settings)
    timeout = getattr(settings, "llm_timeout_seconds", None)
    fallback = _provider_client(route.fallback, timeout) if route.fallback else None
    return RoutedChatClient(route, _provider_client(route.primary, timeout), fallback)


def llm_config_problems(settings: Any = None) -> List[Tuple[str, str]]:
    return route_problems(_settings(settings))


def llm_configured(settings: Any = None) -> bool:
    return not llm_config_problems(settings)
