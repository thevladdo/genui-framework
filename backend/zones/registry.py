"""
Zone Config Registry
Server-side store for governable zone configuration, keyed by (tenant, zone_id).

The architectural inversion (roadmap S1): zone config used to exist only
as request props wired into the host page's code. Anything that must be
approved, versioned, or edited by non-developers (marketing editing
prompts, legal sign-off, per-tenant overrides) must be DATA, not code —
and this store is that data. When an APPROVED entry exists, the render
path serves exactly its config; host props remain the fallback, so
integrations that pass props keep working unchanged.

Record shape:
    {"version": N, "status": "draft"|"approved", "config": {...}, "updated_at": iso}

version increments on every upsert. Renders only ever serve
status="approved"; drafts are the hook for the approval workflow and
preview (phase 2).

Backends follow the profile store pattern: Redis when configured (shared
across workers, survives restarts), in-memory fallback otherwise, always
failing open — a registry outage degrades to host props, never to a 500.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from utils.redis_conn import shared_redis

STATUS_DRAFT = "draft"
STATUS_APPROVED = "approved"
_STATUSES = (STATUS_DRAFT, STATUS_APPROVED)


class ZoneConfig(BaseModel):
    """
    The governed subset of a zone's configuration.

    Exactly the developer-controlled fields governance needs to own:
    prompts, pinned content, rendering constraints. Page context
    (current_page, page_metadata) stays a request prop because it is
    per-request by nature; custom_components stay props because they are
    bound to React components that only exist in the host bundle.

    extra="forbid": a typo'd key must fail at write time, not silently
    leave a field ungoverned.
    """

    model_config = {"extra": "forbid"}

    base_prompt: str = "Show relevant content for this user"
    context_prompt: Optional[str] = None
    pinned_content: List[Dict[str, Any]] = Field(default_factory=list)
    preferred_component_type: Optional[str] = None
    max_items: int = 6
    max_components: Optional[int] = None


class ZoneConfigStore:
    """Async zone config storage with Redis or in-memory backend."""

    def __init__(self, redis_url: Optional[str] = None, key_prefix: str = "genui:zonecfg:"):
        self.key_prefix = key_prefix
        self._conn = shared_redis(redis_url)
        self._memory: Dict[str, Dict[str, Any]] = {}

    def _key(self, tenant: str, zone_id: str) -> str:
        return f"{self.key_prefix}{tenant}:{zone_id}"

    async def get(self, tenant: str, zone_id: str) -> Optional[Dict[str, Any]]:
        """The full record regardless of status (CRUD/preview), or None."""
        key = self._key(tenant, zone_id)

        redis = await self._conn.get()
        if redis is not None:
            try:
                raw = await redis.get(key)
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                try:
                    return json.loads(raw) if raw else None
                except ValueError:
                    return None  # corrupt entry = no config; next upsert rewrites it

        return self._memory.get(key)

    async def get_approved(self, tenant: str, zone_id: str) -> Optional[Dict[str, Any]]:
        """
        The record only if it is APPROVED — the render path's view.

        The "renders only serve approved config" rule lives here, once,
        so phase-2 preview endpoints can read drafts via get() without
        ever being able to leak one into a served render by accident.
        """
        record = await self.get(tenant, zone_id)
        if record is not None and record.get("status") == STATUS_APPROVED:
            return record
        return None

    async def upsert(
        self,
        tenant: str,
        zone_id: str,
        config: Dict[str, Any],
        status: str = STATUS_APPROVED,
    ) -> Dict[str, Any]:
        """
        Write a new version of a zone's governed config.

        The config is normalized through ZoneConfig, so the stored record
        always carries the FULL governed block (defaults materialized):
        the record is the complete truth of what was approved — host
        props never fill gaps in a governed entry.
        """
        if status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}, got {status!r}")
        normalized = ZoneConfig(**config).model_dump()
        current = await self.get(tenant, zone_id)
        record = {
            "version": (current["version"] + 1) if current else 1,
            "status": status,
            "config": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._write(tenant, zone_id, record)
        return record

    async def delete(self, tenant: str, zone_id: str) -> bool:
        """Remove a zone's registry entry. True if it existed."""
        key = self._key(tenant, zone_id)
        existed = False

        redis = await self._conn.get()
        if redis is not None:
            try:
                existed = bool(await redis.delete(key))
            except Exception as e:
                await self._conn.mark_failure(e)

        if key in self._memory:
            del self._memory[key]
            existed = True

        return existed

    async def _write(self, tenant: str, zone_id: str, record: Dict[str, Any]) -> None:
        key = self._key(tenant, zone_id)

        redis = await self._conn.get()
        if redis is not None:
            try:
                await redis.set(key, json.dumps(record, default=str))
                return
            except Exception as e:
                await self._conn.mark_failure(e)

        self._memory[key] = record
