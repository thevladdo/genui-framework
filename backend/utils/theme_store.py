"""
Per-Tenant Theme Store

TenantTheme mirrors the Playground whitelist (studio/src/lib/theme.ts)
token by token: the same tokens, the same per-key shape. That is a
security contract, not tidiness. These values end up as CSS custom
property VALUES on a host page, so each one is pattern-bound to something
that cannot close a declaration or reach url(): a stored theme can
restyle, it can never inject CSS. Anything outside the contract is
rejected at write time (extra="forbid") and re-checked on read, because
Redis is shared infrastructure and this store's output crosses back into
a browser.

The disclosure tokens follow the same rule with one addition: their
shapes also carry a readability floor, because the notice they style is
a transparency obligation and a knob that can hide it is a knob that
defeats it.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError

from utils.tenant_json_store import TenantJsonStore

logger = logging.getLogger(__name__)

# Sizes are px, colors are 6-digit hex: both are closed shapes.
_PX = r"^\d{1,3}px$"
_HEX = r"^#[0-9a-fA-F]{6}$"
_FONT_STACK = r"^[A-Za-z0-9 ,.'\"_-]{1,200}$"
_DISCLOSURE_PX = r"^(1[1-9]|2[0-4])px$"
_DISCLOSURE_OPACITY = r"^(0\.[6-9][0-9]?|1|1\.0+)$"


class TenantTheme(BaseModel):
    """
    The library's GenUITheme tokens the Playground can actually produce.

    Every token is optional and omitted when unset, exactly like the
    Playground export: an unset token means "the library default (or the
    mode block) wins", never "override with empty".
    """

    model_config = {"extra": "forbid"}

    mode: Optional[str] = Field(default=None, pattern=r"^(dark|light)$")
    borderRadius: Optional[str] = Field(default=None, pattern=_PX)
    radiusSm: Optional[str] = Field(default=None, pattern=_PX)
    radiusLg: Optional[str] = Field(default=None, pattern=_PX)
    radiusFull: Optional[str] = Field(default=None, pattern=_PX)
    glassBlur: Optional[str] = Field(default=None, pattern=_PX)
    spacingScale: Optional[str] = Field(default=None, pattern=r"^(sm|base|lg)$")
    accentColor: Optional[str] = Field(default=None, pattern=_HEX)
    fontFamily: Optional[str] = Field(default=None, pattern=_FONT_STACK)
    fontWeightHeading: Optional[str] = Field(default=None, pattern=r"^[1-9]00$")
    successColor: Optional[str] = Field(default=None, pattern=_HEX)
    errorColor: Optional[str] = Field(default=None, pattern=_HEX)
    surface1: Optional[str] = Field(default=None, pattern=_HEX)
    surface2: Optional[str] = Field(default=None, pattern=_HEX)
    surface3: Optional[str] = Field(default=None, pattern=_HEX)
    textOnAccent: Optional[str] = Field(default=None, pattern=_HEX)
    disclosureEnabled: Optional[str] = Field(default=None, pattern=r"^(on|off)$")
    disclosurePosition: Optional[str] = Field(
        default=None, pattern=r"^(above|below)-(left|center|right)$"
    )
    disclosureText: Optional[str] = Field(default=None, max_length=120)
    disclosureFontSize: Optional[str] = Field(default=None, pattern=_DISCLOSURE_PX)
    disclosureOpacity: Optional[str] = Field(default=None, pattern=_DISCLOSURE_OPACITY)

    def tokens(self) -> Dict[str, Any]:
        """Only the tokens actually set, ready to be a theme prop."""
        return self.model_dump(exclude_none=True)


class ThemeStore:
    """Per-tenant theme record: {"theme": {...}, "updated_at": iso}."""

    def __init__(self, redis_url: Optional[str] = None, key_prefix: str = "genui:theme:"):
        self.key_prefix = key_prefix
        self._store = TenantJsonStore(key_prefix, redis_url)

    async def get(self, tenant: str) -> Optional[Dict[str, Any]]:
        """
        This tenant's stored record, or None when nothing valid is stored.

        The stored theme is re-validated here: what this store hands back
        is always inside the contract, whatever ended up in Redis.
        """
        document = await self._store.get(tenant)
        if not isinstance(document, dict) or not isinstance(document.get("theme"), dict):
            return None
        try:
            theme = TenantTheme(**document["theme"]).tokens()
        except ValidationError:
            logger.warning(
                "Stored theme for tenant %r is outside the token contract and "
                "was ignored; save it again from the Studio to replace it.",
                tenant,
            )
            return None
        return {"theme": theme, "updated_at": document.get("updated_at")}

    async def set(self, tenant: str, theme: TenantTheme) -> Dict[str, Any]:
        """Replace this tenant's theme; returns the stored record."""
        record = {
            "theme": theme.tokens(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._store.set(tenant, record)
        return record

    async def storage_backend(self) -> str:
        """'redis' or 'memory'; the Studio warns when a write lives in one worker."""
        return await self._store.storage_backend()


_STORE: Optional[ThemeStore] = None


def get_theme_store() -> ThemeStore:
    """Process-wide singleton, redis_url resolved lazily so the store class
    stays importable without app config (pure-stdlib test shell)."""
    global _STORE
    if _STORE is None:
        from config import settings

        _STORE = ThemeStore(redis_url=settings.redis_url)
    return _STORE
