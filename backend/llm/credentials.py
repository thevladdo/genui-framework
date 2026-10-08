"""
Whether the providers accept the configured keys, asked at startup and then every few minutes.

Readiness reads the last answer and never waits on the network.
The probe reads the model's metadata and spends no tokens.
An endpoint that does not answer, or a compatible server without the models route, gives no verdict: the first is an outage, which the error counters show.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from .routing import LLMConfigError, Role, resolve_route, role_variable

logger = logging.getLogger(__name__)

RECHECK_SECONDS = 300
_PROBE_TIMEOUT = 10.0
_KEY_VARIABLE = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY"}
_EMBEDDINGS = "embeddings"

Probe = Callable[[str, str, Optional[str], Optional[str]], Awaitable[None]]
Target = Tuple[str, str, Optional[str], Optional[str]]

_problems: List[Tuple[str, str]] = []


def problems() -> List[Tuple[str, str]]:
    return list(_problems)


async def _sdk_probe(provider: str, model: str, api_key: Optional[str], base_url: Optional[str]) -> None:
    if provider == "anthropic":
        from anthropic import AsyncAnthropic
        await AsyncAnthropic(api_key=api_key, timeout=_PROBE_TIMEOUT).models.retrieve(model)
        return
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key or "sk-no-key-required", base_url=base_url, timeout=_PROBE_TIMEOUT)
    await client.models.retrieve(model)


def _targets(settings) -> Dict[Target, List[Tuple[str, str, str]]]:
    """(provider, model, key, base url) -> [(who uses it, key variable, model variable)]"""
    found: Dict[Target, List[Tuple[str, str, str]]] = {}
    for role in Role:
        try:
            route = resolve_route(role, settings)
        except LLMConfigError:
            continue
        for target, variable in ((route.primary, route.variable), (route.fallback, f"{role_variable(role)}_FALLBACK")):
            if target is not None:
                found.setdefault((target.provider, target.model, target.api_key, target.base_url), []).append(
                    (role.value, _KEY_VARIABLE[target.provider], variable)
                )

    from .embeddings import EmbeddingConfigError, resolve_embedding_config
    try:
        config = resolve_embedding_config(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            dimensions=settings.embedding_dimensions,
            openai_api_key=settings.openai_api_key,
            google_api_key=settings.google_api_key,
            openai_base_url=settings.openai_base_url,
        )
    except EmbeddingConfigError:
        return found
    key_variable = "EMBEDDING_API_KEY" if settings.embedding_api_key else _KEY_VARIABLE[config.provider]
    found.setdefault((config.provider, config.model, config.api_key, config.base_url), []).append(
        (_EMBEDDINGS, key_variable, "EMBEDDING_MODEL")
    )
    return found


async def _verdict(probe: Probe, target: Target) -> Optional[str]:
    provider, model, api_key, base_url = target
    try:
        await probe(provider, model, api_key, base_url)
    except Exception as e:
        status = getattr(e, "status_code", None)
        # Google answers an invalid key with a 400 that names it
        if status in (401, 403) or (status == 400 and provider == "gemini" and "API key" in str(e)):
            return f"{provider} rejected the key"
        # A compatible server may simply not serve /models/{id}: only the provider's own endpoint gets a 404 verdict
        if status == 404 and (provider == "anthropic" or (provider == "openai" and not base_url)):
            return f"model {model} is not known to {provider}"
        logger.info("Key check for %s %s gave no verdict: %s", provider, model, e)
    return None


async def check(settings=None, probe: Optional[Probe] = None) -> List[Tuple[str, str]]:
    global _problems
    if settings is None:
        from config import settings
    targets = _targets(settings)
    verdicts = await asyncio.gather(*(_verdict(probe or _sdk_probe, target) for target in targets))

    grouped: Dict[Tuple[str, str, bool], List[str]] = {}
    for target, reason in zip(targets, verdicts):
        if reason is None:
            continue
        for user, key_variable, model_variable in targets[target]:
            variable = key_variable if reason.endswith("rejected the key") else model_variable
            grouped.setdefault((variable, reason, user == _EMBEDDINGS), []).append(user)

    order = [role.value for role in Role] + [_EMBEDDINGS]
    found = [
        (f"{', '.join(sorted(set(users), key=order.index))} ({variable})", reason)
        for (variable, reason, _), users in grouped.items()
    ]
    if found != _problems:
        for where, why in found:
            logger.error("LLM key check: %s: %s", where, why)
        if not found:
            logger.info("LLM key check: every key accepted")
    _problems = found
    return found


async def watch(settings=None) -> None:
    while True:
        await asyncio.sleep(RECHECK_SECONDS)
        try:
            await check(settings)
        except Exception:
            logger.warning("LLM key check failed", exc_info=True)
