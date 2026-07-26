"""
Per-Tenant Content Policy Store

The banned-term matcher there reads a CONTENT_POLICY env string and stays pure;
a compliance owner cannot edit an env var without infra access and a redeploy, which
is not governance. This store makes the policy live DATA, edited per
tenant by an admin over an API and enforced immediately, with the env
kept as the deployment-wide seed.
"""

from typing import List, Optional

from utils.content_policy import ContentPolicy, policy_for
from utils.tenant_json_store import TenantJsonStore


def _normalize(terms: List[str]) -> List[str]:
    """Strip, drop empties, dedup preserving order. Order-preserving dict."""
    out = {}
    for term in terms:
        cleaned = str(term).strip()
        if cleaned and cleaned not in out:
            out[cleaned] = None
    return list(out)


class ContentPolicyStore:
    """Per-tenant banned-term list. Redis or in-memory, fail-open."""

    def __init__(self, redis_url: Optional[str] = None, key_prefix: str = "genui:contentpolicy:"):
        self.key_prefix = key_prefix
        self._store = TenantJsonStore(key_prefix, redis_url)

    async def get(self, tenant: str) -> List[str]:
        """This tenant's stored banned terms, or [] when none/unreachable."""
        document = await self._store.get(tenant) or {}
        return [str(t) for t in document.get("banned_terms", [])]

    async def set(self, tenant: str, terms: List[str]) -> List[str]:
        """Replace this tenant's banned terms; returns the normalized list."""
        normalized = _normalize(terms)
        await self._store.set(tenant, {"banned_terms": normalized})
        return normalized

    async def storage_backend(self) -> str:
        """'redis' or 'memory'; the Studio warns when a write lives in one worker."""
        return await self._store.storage_backend()


_STORE: Optional[ContentPolicyStore] = None


def get_content_policy_store() -> ContentPolicyStore:
    """Process-wide singleton, redis_url resolved lazily so the store class
    stays importable without app config (pure-stdlib test shell)."""
    global _STORE
    if _STORE is None:
        from config import settings

        _STORE = ContentPolicyStore(redis_url=settings.redis_url)
    return _STORE


async def effective_policy(tenant: Optional[str], env_raw: str) -> ContentPolicy:
    """
    The policy the serving path enforces: env (policy_for, unchanged) plus
    this tenant's stored terms. Drop-in async replacement for policy_for.
    """
    stored = await get_content_policy_store().get(tenant or "default")
    env = policy_for(tenant, env_raw)
    return ContentPolicy(env.banned_terms + list(stored))
