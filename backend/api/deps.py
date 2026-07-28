"""
Shared service singletons for API routers.
"""

from typing import Optional

from fastapi import HTTPException

from auth import AuthContext
from config import settings
from profiles import ProfileStore
from utils.rate_limit import RateLimiter
from zones import ZoneConfigStore

_profile_store: Optional[ProfileStore] = None
_zone_config_store: Optional[ZoneConfigStore] = None
_llm_budget: Optional[RateLimiter] = None


def get_profile_store() -> ProfileStore:
    """Get or create the server-side profile store singleton."""
    global _profile_store
    if _profile_store is None:
        _profile_store = ProfileStore(
            redis_url=settings.redis_url,
            ttl_seconds=settings.profile_ttl_seconds,
        )
    return _profile_store


def get_zone_config_store() -> ZoneConfigStore:
    """Get or create the zone config registry singleton."""
    global _zone_config_store
    if _zone_config_store is None:
        _zone_config_store = ZoneConfigStore(redis_url=settings.redis_url)
    return _zone_config_store


def get_llm_budget() -> RateLimiter:
    """
    Per-tenant hourly cap on LLM generations (LLM_BUDGET_PER_HOUR).

    Reuses the fixed-window rate limiter on the shared Redis store.
    Identity = tenant: the cap protects the tenant's BYOK key, not a single client key.
    """
    global _llm_budget
    if _llm_budget is None:
        _llm_budget = RateLimiter(
            limit=settings.llm_budget_per_hour,
            window_seconds=3600,
            redis_url=settings.redis_url,
            key_prefix="genui:llmbudget:",
        )
    return _llm_budget


def budget_tenant(auth: AuthContext) -> Optional[str]:
    """Tenant to charge for a generation; None (exempt) for admin keys."""
    return None if auth.is_admin else auth.tenant


async def charge_llm_budget(tenant: Optional[str], cost: int = 1) -> None:
    """
    Charge `cost` generations to the tenant budget; 429 when exhausted.

    Called exactly where generations are born, never on cache hits: the
    cost is controlled at its source. Cost is the number of model calls
    the request is about to make, so one request that fans out to
    several agents is charged for all of them.
    """
    if tenant is None:
        return
    if not await get_llm_budget().allow(tenant, cost=cost):
        raise HTTPException(
            status_code=429,
            detail=f"LLM budget exceeded (LLM_BUDGET_PER_HOUR="
                   f"{settings.llm_budget_per_hour}): no new generations "
                   f"until the window resets, raise the cap or wait. Cached "
                   f"zone renders keep being served; a chat answer needs a "
                   f"generation, so it stops",
        )
