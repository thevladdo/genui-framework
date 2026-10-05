"""
Which provider and model serves each kind of model call.

Every call to a model declares a role, and the role is the only routing key.
Pure: no framework imports, settings come in as any object with the setting attributes, so it runs and is tested without the backend venv.

Configuration, per role (LLM_ZONE, LLM_CHAT, LLM_PROFILE, LLM_BEHAVIOR, LLM_CONTEXT, LLM_SUMMARY):

    LLM_<ROLE>=provider:model     a provider and a model for this role
    LLM_<ROLE>=model              a model on LLM_PROVIDER
    LLM_<ROLE>_FALLBACK=...       same forms; the only way a call may move to another model

Unset, a role keeps LLM_PROVIDER and its historical model setting (RESPONSE_MODEL, PROFILE_MODEL, CONTEXT_MODEL).
Keys and endpoints belong to the provider (OPENAI_API_KEY + OPENAI_BASE_URL, ANTHROPIC_API_KEY, GOOGLE_API_KEY), not to the role.
A provider name that is not known is a configuration error, never a guess.
"""

import importlib.util
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

PROVIDERS = ("openai", "anthropic", "gemini", "google")

_KEY_SETTING = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "google_api_key",
}


class Role(str, Enum):
    ZONE = "zone"
    CHAT = "chat"
    PROFILE = "profile"
    BEHAVIOR = "behavior"
    CONTEXT = "context"
    SUMMARY = "summary"


_DEFAULT_MODEL_SETTING = {
    Role.ZONE: "response_model",
    Role.CHAT: "response_model",
    Role.PROFILE: "profile_model",
    Role.BEHAVIOR: "profile_model",
    Role.CONTEXT: "context_model",
    Role.SUMMARY: "profile_model",
}


class LLMConfigError(ValueError):
    def __init__(self, reason: str, role: Optional["Role"] = None, variable: Optional[str] = None):
        self.reason, self.role, self.variable = reason, role, variable
        super().__init__(f"role {role.value} ({variable}): {reason}" if role else reason)


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: Optional[str]
    base_url: Optional[str]


@dataclass(frozen=True)
class Target:
    provider: str
    model: str
    api_key: Optional[str]
    base_url: Optional[str]


@dataclass(frozen=True)
class Route:
    role: Role
    primary: Target
    fallback: Optional[Target]
    variable: str


def resolve_provider_config(
    provider: Optional[str],
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> ProviderConfig:
    normalized = (provider or "openai").strip().lower()
    if normalized not in PROVIDERS:
        raise LLMConfigError(
            f"unknown LLM provider {provider!r} (known: openai, anthropic, gemini)"
        )
    if normalized == "anthropic":
        return ProviderConfig("anthropic", anthropic_api_key, None)
    if normalized in ("gemini", "google"):
        return ProviderConfig("gemini", google_api_key, GEMINI_OPENAI_BASE_URL)
    return ProviderConfig("openai", openai_api_key, openai_base_url)


def provider_configured(config: Any) -> bool:
    """Gemini's fixed Google base_url does not make it keyless: only an OpenAI-compatible endpoint can be."""
    if config.api_key:
        return True
    return config.provider == "openai" and bool(config.base_url)


def role_variable(role: Role) -> str:
    return f"LLM_{Role(role).value.upper()}"


def _target(provider: str, model: str, settings: Any) -> Target:
    config = resolve_provider_config(
        provider,
        openai_api_key=getattr(settings, "openai_api_key", None),
        anthropic_api_key=getattr(settings, "anthropic_api_key", None),
        google_api_key=getattr(settings, "google_api_key", None),
        openai_base_url=getattr(settings, "openai_base_url", None),
    )
    return Target(config.provider, model, config.api_key, config.base_url)


def parse_spec(value: str, default_provider: str) -> Tuple[str, str]:
    """
    "provider:model" or "model" -> (provider, model).

    Only a known provider counts as a prefix, so a model whose name has a colon (Ollama tags) is written after one: openai:qwen3:8b.
    A prefix that is not a provider is an error rather than a model name: a misspelt provider must not send prompts to the default one.
    """
    value = value.strip()
    head, sep, tail = value.partition(":")
    if not sep:
        provider, model = default_provider, value
    elif head.strip().lower() in PROVIDERS:
        provider, model = head.strip().lower(), tail.strip()
    else:
        raise LLMConfigError(
            f"{value!r}: {head!r} is not a provider (openai, anthropic, gemini); "
            f"write provider:model, for example openai:{value}"
        )
    if not model:
        raise LLMConfigError(f"{value!r}: no model after the provider")
    return provider, model


def resolve_route(role: Role, settings: Any) -> Route:
    role = Role(role)
    variable = role_variable(role)
    default_provider = getattr(settings, "llm_provider", None) or "openai"
    spec = getattr(settings, f"llm_{role.value}", None)

    stage = decided_by = variable
    try:
        if spec and spec.strip():
            provider, model = parse_spec(spec, default_provider)
        else:
            # The historical settings are a bare model name, colons included, never parsed
            model_setting = _DEFAULT_MODEL_SETTING[role]
            provider, model = default_provider, getattr(settings, model_setting)
            stage = decided_by = f"LLM_PROVIDER/{model_setting.upper()}"
        primary = _target(provider, model, settings)
        fallback = None
        fallback_spec = getattr(settings, f"llm_{role.value}_fallback", None)
        if fallback_spec and fallback_spec.strip():
            stage = f"{variable}_FALLBACK"
            fallback = _target(*parse_spec(fallback_spec, default_provider), settings)
    except LLMConfigError as e:
        raise LLMConfigError(e.reason, role, stage) from None

    return Route(role, primary, fallback, decided_by)


def sdk_installed(provider: str) -> bool:
    return provider != "anthropic" or importlib.util.find_spec("anthropic") is not None


def _missing_key(target: Target) -> str:
    if target.provider == "openai":
        return "no OPENAI_API_KEY and no OPENAI_BASE_URL"
    return f"no {_KEY_SETTING[target.provider].upper()}"


def route_problems(settings: Any) -> List[Tuple[str, str]]:
    """
    Every role that cannot be called as configured, as (where, why).

    `where` names the roles and the variable and is safe to show on an unauthenticated probe.
    `why` names the provider and the missing key, for the operator's logs.
    Roles failing for the same reason are grouped, so a missing global key reads as one problem.
    """
    grouped: Dict[Tuple[str, str], List[str]] = {}
    for role in Role:
        try:
            route = resolve_route(role, settings)
        except LLMConfigError as e:
            grouped.setdefault((e.variable, e.reason), []).append(role.value)
            continue
        targets = [(route.variable, route.primary, "provider")]
        if route.fallback:
            targets.append((f"{role_variable(role)}_FALLBACK", route.fallback, "fallback provider"))
        for variable, target, what in targets:
            if not provider_configured(target):
                reason = f"{what} {target.provider} has {_missing_key(target)}"
            elif not sdk_installed(target.provider):
                reason = f"{what} {target.provider} needs the 'anthropic' package in the image"
            else:
                continue
            grouped.setdefault((variable, reason), []).append(role.value)

    return [
        (f"{', '.join(roles)} ({variable})", reason)
        for (variable, reason), roles in grouped.items()
    ]
