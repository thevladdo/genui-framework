"""
Zone Config Registry
Server-side store for governable zone configuration, keyed by (tenant, zone_id).

The architectural inversion: zone config used to exist only
as request props wired into the host page's code. Anything that must be
approved, versioned, or edited by non-developers (marketing editing
prompts, legal sign-off, per-tenant overrides) must be DATA, not code —
and this store is that data. When an APPROVED entry exists, the render
path serves exactly its config; host props remain the fallback, so
integrations that pass props keep working unchanged.

Record shape:
    {"version": N, "status": "draft"|"approved", "config": {...}, "updated_at": iso}

version increments on every write. Renders only ever serve
status="approved".

Backends follow the profile store pattern: Redis when configured (shared
across workers, survives restarts), in-memory fallback otherwise, always
failing open — a registry outage degrades to host props, never to a 500.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from utils.redis_conn import shared_redis

STATUS_DRAFT = "draft"
STATUS_APPROVED = "approved"
_STATUSES = (STATUS_DRAFT, STATUS_APPROVED)
_DRAFT_SUFFIX = ":draft"
_OBSERVED_MAX = 1000


class VersionConflict(Exception):
    """Optimistic-concurrency failure: the caller edited a stale version."""


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
        self.observed_prefix = "genui:zoneobs:"
        self._conn = shared_redis(redis_url)
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._memory_observed: Dict[str, Set[str]] = {}

    def _key(self, tenant: str, zone_id: str) -> str:
        return f"{self.key_prefix}{tenant}:{zone_id}"

    def _draft_key(self, tenant: str, zone_id: str) -> str:
        return self._key(tenant, zone_id) + _DRAFT_SUFFIX

    def _observed_key(self, tenant: str) -> str:
        return f"{self.observed_prefix}{tenant}"

    async def _read(self, key: str) -> Optional[Dict[str, Any]]:
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

    async def get(self, tenant: str, zone_id: str) -> Optional[Dict[str, Any]]:
        """The full main-slot record regardless of status (CRUD/preview), or None."""
        return await self._read(self._key(tenant, zone_id))

    async def get_draft(self, tenant: str, zone_id: str) -> Optional[Dict[str, Any]]:
        """The work-in-progress record, or None. Never served to clients."""
        return await self._read(self._draft_key(tenant, zone_id))

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
        record = {
            "version": await self._next_version(tenant, zone_id),
            "status": status,
            "config": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._write(self._key(tenant, zone_id), record)
        return record

    async def save_draft(
        self,
        tenant: str,
        zone_id: str,
        config: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Write the draft slot WITHOUT touching what production serves.

        This is the write the governance UI uses: an edit must never
        silently un-approve the config a legal/marketing sign-off put in
        production; only approve() changes the served record.

        expected_version enables optimistic concurrency (phase-2 plan):
        pass the latest version you loaded; a mismatch raises
        VersionConflict instead of overwriting someone else's edit.
        Read-modify-write without a lock is deliberate: governance edits
        happen at human speed.
        """
        normalized = ZoneConfig(**config).model_dump()
        current = await self._current_version(tenant, zone_id)
        if expected_version is not None and expected_version != current:
            raise VersionConflict(
                f"expected version {expected_version}, but the latest is "
                f"{current}: reload before editing"
            )
        record = {
            "version": current + 1,
            "status": STATUS_DRAFT,
            "config": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._write(self._draft_key(tenant, zone_id), record)
        return record

    async def approve(
        self,
        tenant: str,
        zone_id: str,
        expected_version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Promote the draft into the served (main) slot.

        The ONLY path from draft to approved: the approved record is the
        draft verbatim with its status flipped, so what was previewed is
        exactly what production starts serving. Returns None when there
        is nothing to approve. Also accepts a phase-1 legacy draft
        written to the main slot via upsert(status="draft").
        """
        draft = await self.get_draft(tenant, zone_id)
        legacy = False
        if draft is None:
            main = await self.get(tenant, zone_id)
            if main is None or main.get("status") != STATUS_DRAFT:
                return None
            draft, legacy = main, True

        current = await self._current_version(tenant, zone_id)
        if expected_version is not None and expected_version != current:
            raise VersionConflict(
                f"expected version {expected_version}, but the latest is "
                f"{current}: reload before approving"
            )

        record = {
            "version": draft["version"],
            "status": STATUS_APPROVED,
            "config": draft["config"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._write(self._key(tenant, zone_id), record)
        if not legacy:
            await self._delete_key(self._draft_key(tenant, zone_id))
        return record

    async def discard_draft(self, tenant: str, zone_id: str) -> bool:
        """Drop the draft slot; the approved record is untouched."""
        return await self._delete_key(self._draft_key(tenant, zone_id))

    async def delete(self, tenant: str, zone_id: str) -> bool:
        """Remove a zone's registry entry (draft included). True if it existed."""
        main_existed = await self._delete_key(self._key(tenant, zone_id))
        draft_existed = await self._delete_key(self._draft_key(tenant, zone_id))
        return main_existed or draft_existed

    async def list_zones(self, tenant: str) -> Dict[str, Dict[str, Any]]:
        """
        Registry entries for a tenant: zone_id -> {status, version,
        updated_at, has_draft}. status is what production does (approved
        = an approved record serves; draft = configured but nothing
        approved yet); version/updated_at follow the LATEST edit (the
        draft when one exists).
        """
        prefix = f"{self.key_prefix}{tenant}:"
        keys = set()
        redis = await self._conn.get()
        if redis is not None:
            try:
                async for key in redis.scan_iter(match=prefix + "*"):
                    keys.add(str(key))
            except Exception as e:
                await self._conn.mark_failure(e)
        keys.update(k for k in self._memory if k.startswith(prefix))

        zone_ids = set()
        for key in keys:
            rest = key[len(prefix):]
            if rest.endswith(_DRAFT_SUFFIX):
                rest = rest[: -len(_DRAFT_SUFFIX)]
            zone_ids.add(rest)

        entries: Dict[str, Dict[str, Any]] = {}
        for zone_id in zone_ids:
            main = await self.get(tenant, zone_id)
            draft = await self.get_draft(tenant, zone_id)
            if main is None and draft is None:
                continue
            latest = draft or main
            entries[zone_id] = {
                "status": main["status"] if main else STATUS_DRAFT,
                "version": latest["version"],
                "updated_at": latest["updated_at"],
                "has_draft": draft is not None
                or (main is not None and main["status"] == STATUS_DRAFT),
            }
        return entries

    async def record_observed(self, tenant: str, zone_id: str) -> None:
        """
        Remember that the render path served this (tenant, zone_id).

        zone_id is LOGICAL identity: five mounts of zoneId="hero" are one
        zone, and a SET dedups for free. Called on the serving path, so
        it fails open like every store operation.
        """
        key = self._observed_key(tenant)
        redis = await self._conn.get()
        if redis is not None:
            try:
                if await redis.scard(key) < _OBSERVED_MAX:
                    await redis.sadd(key, zone_id)
                return
            except Exception as e:
                await self._conn.mark_failure(e)
        seen = self._memory_observed.setdefault(tenant, set())
        if len(seen) < _OBSERVED_MAX:
            seen.add(zone_id)

    async def observed(self, tenant: str) -> Set[str]:
        """Every zone_id this tenant's site was actually served."""
        redis = await self._conn.get()
        if redis is not None:
            try:
                members = await redis.smembers(self._observed_key(tenant))
                return {str(m) for m in members}
            except Exception as e:
                await self._conn.mark_failure(e)
        return set(self._memory_observed.get(tenant, set()))

    async def storage_backend(self) -> str:
        """
        'redis' or 'memory'. Governance writes landing in the in-memory
        fallback live in ONE worker and die with it: the CRUD API
        reports this so the Studio can warn instead of losing an
        approval in silence.
        """
        return "redis" if await self._conn.get() is not None else "memory"

    async def _current_version(self, tenant: str, zone_id: str) -> int:
        main = await self.get(tenant, zone_id)
        draft = await self.get_draft(tenant, zone_id)
        return max(
            main["version"] if main else 0,
            draft["version"] if draft else 0,
        )

    async def _next_version(self, tenant: str, zone_id: str) -> int:
        return await self._current_version(tenant, zone_id) + 1

    async def _write(self, key: str, record: Dict[str, Any]) -> None:
        redis = await self._conn.get()
        if redis is not None:
            try:
                await redis.set(key, json.dumps(record, default=str))
                return
            except Exception as e:
                await self._conn.mark_failure(e)

        self._memory[key] = record

    async def _delete_key(self, key: str) -> bool:
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
