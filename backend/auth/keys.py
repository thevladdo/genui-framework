"""
API Key Registry
Key parsing, validation, and tenant resolution, no web framework imports.

Key model (pragmatic for a browser-called API, same approach as
Algolia/Supabase publishable keys):

- client keys: shipped to the browser. They identify the calling app
  (tenant), gate rate limits, and scope cached/stored data. They are
  identifiers more than secrets.
- admin keys: server-to-server only (document ingestion, cache warmup,
  stats). Never expose them in frontend code.

Configuration format (comma-separated env vars):
    CLIENT_API_KEYS=pk_live_abc:acme,pk_live_def:globex
    ADMIN_API_KEYS=sk_live_xyz:acme

Each entry is "key" or "key:tenant"; tenant defaults to "default".
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_TENANT = "default"


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity of an authenticated request."""
    tenant: str
    is_admin: bool
    # Short fingerprint of the key for audit/rate-limit identity.
    # The raw key is never stored or logged.
    key_fingerprint: str


def fingerprint(key: str) -> str:
    """Non-reversible short identifier for a key (for logs and rate limits)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def parse_key_entries(entries: Union[str, Iterable[str], None]) -> Dict[str, str]:
    """
    Parse key entries into {key: tenant}.

    Accepts a comma-separated string or an iterable of "key" / "key:tenant".
    Empty entries are skipped.
    """
    if entries is None:
        return {}
    if isinstance(entries, str):
        entries = entries.split(",")

    parsed: Dict[str, str] = {}
    for entry in entries:
        entry = str(entry).strip()
        if not entry:
            continue
        if ":" in entry:
            key, tenant = entry.split(":", 1)
            key, tenant = key.strip(), tenant.strip() or DEFAULT_TENANT
        else:
            key, tenant = entry, DEFAULT_TENANT
        if key:
            parsed[key] = tenant
    return parsed


class KeyRegistry:
    """Holds configured API keys and resolves them to an AuthContext."""

    def __init__(
        self,
        client_keys: Union[str, Iterable[str], None] = None,
        admin_keys: Union[str, Iterable[str], None] = None,
    ):
        self._client: Dict[str, str] = parse_key_entries(client_keys)
        self._admin: Dict[str, str] = parse_key_entries(admin_keys)

        overlap = set(self._client) & set(self._admin)
        if overlap:
            logger.warning(
                "API keys configured as both client and admin (%d); "
                "they will be treated as admin keys", len(overlap)
            )

    @property
    def enabled(self) -> bool:
        """Auth is enforced only when at least one key is configured."""
        return bool(self._client or self._admin)

    def authenticate(self, key: Optional[str]) -> Optional[AuthContext]:
        """Resolve a presented key. Returns None when the key is unknown."""
        if not key:
            return None
        key = key.strip()

        tenant = self._admin.get(key)
        if tenant is not None:
            return AuthContext(tenant=tenant, is_admin=True, key_fingerprint=fingerprint(key))

        tenant = self._client.get(key)
        if tenant is not None:
            return AuthContext(tenant=tenant, is_admin=False, key_fingerprint=fingerprint(key))

        return None
