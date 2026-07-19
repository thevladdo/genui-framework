"""
LLM client factory: provider selection is configuration, not code.

    LLM_PROVIDER=openai     -> OpenAI (or any OpenAI-compatible endpoint via OPENAI_BASE_URL)
    LLM_PROVIDER=anthropic  -> Anthropic Messages API
    LLM_PROVIDER=gemini     -> Google Gemini through its OpenAI-compatible endpoint (no extra dependency)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .base import LLMChatClient

logger = logging.getLogger(__name__)

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_KNOWN_PROVIDERS = ("openai", "anthropic", "gemini", "google")


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved provider configuration (pure, testable)."""
    provider: str       # "openai" | "anthropic" | "gemini"
    api_key: Optional[str]
    base_url: Optional[str]


def resolve_provider_config(
    provider: str,
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> ProviderConfig:
    """Map settings to a concrete provider configuration."""
    normalized = (provider or "openai").strip().lower()

    if normalized not in _KNOWN_PROVIDERS:
        logger.warning("Unknown LLM_PROVIDER %r, falling back to openai", provider)
        normalized = "openai"

    if normalized == "anthropic":
        return ProviderConfig("anthropic", anthropic_api_key, None)

    if normalized in ("gemini", "google"):
        return ProviderConfig("gemini", google_api_key, GEMINI_OPENAI_BASE_URL)

    return ProviderConfig("openai", openai_api_key, openai_base_url)


def provider_configured(config: ProviderConfig) -> bool:
    """
    Whether this ProviderConfig can actually be called: a key, or a
    keyless OpenAI-compatible endpoint (local vLLM/Ollama). Gemini's
    fixed Google base_url does not count as keyless-capable.
    """
    if config.api_key:
        return True
    return config.provider == "openai" and bool(config.base_url)


def llm_configured() -> bool:
    """
    Config-level health signal for /health and /ready: no network call,
    no spend. Actual provider reachability shows up as
    genui_llm_generations_total{outcome="error"} in /metrics.
    """
    from config import settings

    return provider_configured(
        resolve_provider_config(
            provider=settings.llm_provider,
            openai_api_key=settings.openai_api_key,
            anthropic_api_key=settings.anthropic_api_key,
            google_api_key=settings.google_api_key,
            openai_base_url=settings.openai_base_url,
        )
    )


def create_llm_client(model: str) -> LLMChatClient:
    """Create the configured LLM client for a given model."""
    from config import settings

    config = resolve_provider_config(
        provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        google_api_key=settings.google_api_key,
        openai_base_url=settings.openai_base_url,
    )

    if config.provider == "anthropic":
        from .anthropic_client import AnthropicChatClient
        return AnthropicChatClient(
            api_key=config.api_key,
            model=model,
            timeout=settings.llm_timeout_seconds,
        )

    from .openai_client import OpenAIChatClient
    return OpenAIChatClient(
        api_key=config.api_key,
        model=model,
        base_url=config.base_url,
        provider_name=config.provider,
        timeout=settings.llm_timeout_seconds,
    )
