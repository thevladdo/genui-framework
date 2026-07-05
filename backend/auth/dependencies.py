"""
FastAPI auth dependencies.

Usage:
    @router.post("/render")
    async def render(request: ..., auth: AuthContext = Depends(require_client)):
        ...

Keys are presented in the X-API-Key header (or Authorization: Bearer).
When no keys are configured, auth is OPEN (dev mode) and a warning is
logged once. Production deployments must configure CLIENT_API_KEYS /
ADMIN_API_KEYS.

require_client also enforces the per-key rate limit (admin keys are
exempt), so endpoints get auth + rate limiting from a single dependency.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from config import settings
from utils.audit import AuditLogger
from utils.rate_limit import RateLimiter

from .keys import AuthContext, KeyRegistry

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_header = APIKeyHeader(name="Authorization", auto_error=False)

_registry: Optional[KeyRegistry] = None
_rate_limiter: Optional[RateLimiter] = None
_audit_logger: Optional[AuditLogger] = None
_warned_open = False

# Identity used when auth is not configured (dev mode)
OPEN_CONTEXT = AuthContext(tenant="default", is_admin=True, key_fingerprint="open")


def get_key_registry() -> KeyRegistry:
    global _registry
    if _registry is None:
        _registry = KeyRegistry(
            client_keys=settings.client_api_keys,
            admin_keys=settings.admin_api_keys,
        )
    return _registry


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            limit=settings.rate_limit_per_minute,
            window_seconds=60,
            redis_url=settings.redis_url,
        )
    return _rate_limiter


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(
            path=settings.audit_log_path,
            enabled=settings.audit_log_enabled,
        )
    return _audit_logger


def _extract_key(api_key: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if api_key:
        return api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_client(
    api_key: Optional[str] = Security(_api_key_header),
    authorization: Optional[str] = Security(_bearer_header),
) -> AuthContext:
    """Authenticate a client (or admin) key and apply the rate limit."""
    global _warned_open

    registry = get_key_registry()
    if not registry.enabled:
        if not _warned_open:
            logger.warning(
                "No API keys configured; endpoints are OPEN. "
                "Set CLIENT_API_KEYS / ADMIN_API_KEYS in production."
            )
            _warned_open = True
        return OPEN_CONTEXT

    context = registry.authenticate(_extract_key(api_key, authorization))
    if context is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    if not context.is_admin:
        limiter = get_rate_limiter()
        if not await limiter.allow(context.key_fingerprint):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return context


async def require_admin(
    auth: AuthContext = Depends(require_client),
) -> AuthContext:
    """Restrict an endpoint to admin keys (server-to-server)."""
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin API key required")
    return auth
