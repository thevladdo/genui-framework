"""
Provider factory for the datapizza-based agents (ResponseAgent,
ProfileAgent, BehaveAgent).

datapizza ships one client class per provider; module paths differ
between versions, so candidates are tried in order and unknown setups
fall back to the OpenAI client with a loud warning. A misconfigured
provider must degrade, not crash the chat pipeline.
"""

import importlib
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# (module path, class name) candidates per provider, tried in order
_PROVIDER_CANDIDATES = {
    "anthropic": [
        ("datapizza.clients.anthropic", "AnthropicClient"),
        ("datapizza.clients", "AnthropicClient"),
    ],
    "gemini": [
        ("datapizza.clients.google", "GoogleClient"),
        ("datapizza.clients.vertexai", "VertexAIClient"),
        ("datapizza.clients", "GoogleClient"),
    ],
}
_PROVIDER_CANDIDATES["google"] = _PROVIDER_CANDIDATES["gemini"]


def _try_import(candidates: List[Tuple[str, str]]):
    for module_path, class_name in candidates:
        try:
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError):
            continue
    return None


def create_datapizza_client(model: str, api_key_override: Optional[str] = None):
    """
    Create the datapizza client for the configured LLM_PROVIDER.

    Falls back to the OpenAI client (with a warning) when the provider's
    datapizza client or API key is unavailable.
    """
    from config import settings

    provider = (settings.llm_provider or "openai").strip().lower()

    if provider in _PROVIDER_CANDIDATES:
        api_key = api_key_override or (
            settings.anthropic_api_key if provider == "anthropic"
            else settings.google_api_key
        )
        client_class = _try_import(_PROVIDER_CANDIDATES[provider])

        if client_class is not None and api_key:
            return client_class(api_key=api_key, model=model)

        logger.warning(
            "LLM_PROVIDER=%s requested but datapizza client or API key is "
            "unavailable; falling back to OpenAI", provider
        )

    from datapizza.clients.openai import OpenAIClient

    return OpenAIClient(
        api_key=api_key_override or settings.openai_api_key,
        model=model,
    )
