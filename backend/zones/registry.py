"""
Zone Config Registry
Server-side store for governable zone configuration, keyed by (tenant, zone_id).

Without this store, zone config exists only as request props wired into the host page's code.
Anything approved, versioned or edited by non-developers (marketing editing prompts, legal sign-off, per-tenant overrides) has to be data, and this store holds it.
When an APPROVED entry exists, the render path serves exactly its config; host props remain the fallback, so integrations that pass props keep working unchanged.

Record shape:
    {"version": N, "status": "draft"|"approved", "config": {...}, "updated_at": iso}

version increments on every write.
Renders only ever serve status="approved".

Redis when configured (shared across workers, survives restarts), in-memory otherwise.
An approval cannot be regenerated, and host props in its place would serve exactly what the registry exists to govern: with Redis unreachable a read serves the last version this process read or wrote (an approval, or its known absence) and otherwise raises StoreUnavailable; writes raise.
Every version-checked write reads and writes both slots in one atomic operation (WATCH/MULTI).
"""

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from utils.redis_conn import StoreUnavailable, atomic_update, shared_redis

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
        # Without Redis: the store itself.
        # With Redis: the last version read or written per key, None = known absent.
        self._memory: Dict[str, Optional[Dict[str, Any]]] = {}
        self._memory_observed: Dict[str, Set[str]] = {}

    def _key(self, tenant: str, zone_id: str) -> str:
        return f"{self.key_prefix}{tenant}:{zone_id}"

    def _draft_key(self, tenant: str, zone_id: str) -> str:
        return self._key(tenant, zone_id) + _DRAFT_SUFFIX

    def _observed_key(self, tenant: str) -> str:
        return f"{self.observed_prefix}{tenant}"

    def _in_memory(self) -> bool:
        return self._conn.status == "disabled"

    async def _read(self, key: str) -> Optional[Dict[str, Any]]:
        redis = await self._conn.get()
        if redis is not None:
            try:
                raw = await redis.get(key)
            except Exception as e:
                await self._conn.mark_failure(e)
            else:
                self._memory[key] = _parse(raw)
                return self._memory[key]

        if self._in_memory() or key in self._memory:
            return self._memory.get(key)
        raise StoreUnavailable("zone registry")

    async def _transact(
        self,
        tenant: str,
        zone_id: str,
        decide: Callable[
            [Optional[Dict[str, Any]], Optional[Dict[str, Any]]],
            Tuple[Dict[str, Optional[Dict[str, Any]]], Any],
        ],
    ) -> Any:
        """
        decide(main, draft) -> ({slot key: record, or None to delete}, result).

        The version check inside `decide` and the writes it returns are one operation: a concurrent write to either slot between the read and the write makes Redis run `decide` again on the new records.
        In memory nothing awaits between the read and the write.
        """
        main_key, draft_key = self._key(tenant, zone_id), self._draft_key(tenant, zone_id)
        if self._in_memory():
            writes, result = decide(self._memory.get(main_key), self._memory.get(draft_key))
            for key, record in writes.items():
                if record is None:
                    self._memory.pop(key, None)
                else:
                    self._memory[key] = record
            return result

        written: Dict[str, Optional[Dict[str, Any]]] = {}

        def on_values(values):
            writes, result = decide(*(_parse(v) for v in values))
            written.clear()
            written.update(writes)
            return {
                key: None if record is None else (json.dumps(record, default=str), None)
                for key, record in writes.items()
            }, result

        result = await atomic_update(
            self._conn, [main_key, draft_key], on_values, "zone registry"
        )
        self._memory.update(written)
        return result

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

        def decide(main, draft):
            record = {
                "version": _version(main, draft) + 1,
                "status": status,
                "config": normalized,
                "updated_at": _now(),
            }
            return {self._key(tenant, zone_id): record}, record

        return await self._transact(tenant, zone_id, decide)

    async def save_draft(
        self,
        tenant: str,
        zone_id: str,
        config: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Write the draft slot WITHOUT touching what production serves.

        This is the write the governance UI uses: an edit must never silently un-approve the config a legal/marketing sign-off put in production; only approve() changes the served record.

        expected_version enables optimistic concurrency: pass the latest version you loaded; a mismatch raises VersionConflict instead of overwriting someone else's edit.
        """
        normalized = ZoneConfig(**config).model_dump()

        def decide(main, draft):
            current = _version(main, draft)
            _check_version(expected_version, current, "editing")
            record = {
                "version": current + 1,
                "status": STATUS_DRAFT,
                "config": normalized,
                "updated_at": _now(),
            }
            return {self._draft_key(tenant, zone_id): record}, record

        return await self._transact(tenant, zone_id, decide)

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
        def decide(main, draft):
            source = draft
            if source is None:
                if main is None or main.get("status") != STATUS_DRAFT:
                    return {}, None
                source = main
            _check_version(expected_version, _version(main, draft), "approving")
            record = {
                "version": source["version"],
                "status": STATUS_APPROVED,
                "config": source["config"],
                "updated_at": _now(),
            }
            writes = {self._key(tenant, zone_id): record}
            if draft is not None:
                writes[self._draft_key(tenant, zone_id)] = None
            return writes, record

        return await self._transact(tenant, zone_id, decide)

    async def discard_draft(self, tenant: str, zone_id: str) -> bool:
        """Drop the draft slot; the approved record is untouched."""
        return await self._delete_key(self._draft_key(tenant, zone_id))

    async def delete(
        self, tenant: str, zone_id: str, expected_version: Optional[int] = None
    ) -> bool:
        """
        Remove a zone's registry entry (draft included).
        True if it existed.
        With expected_version, a newer edit or approval raises VersionConflict.
        """
        def decide(main, draft):
            if main is None and draft is None:
                return {}, False
            _check_version(expected_version, _version(main, draft), "deleting")
            return {
                self._key(tenant, zone_id): None,
                self._draft_key(tenant, zone_id): None,
            }, True

        return await self._transact(tenant, zone_id, decide)

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
        if self._in_memory():
            keys.update(k for k in self._memory if k.startswith(prefix))
        else:
            redis = await self._conn.get()
            if redis is None:
                raise StoreUnavailable("zone registry")
            try:
                async for key in redis.scan_iter(match=prefix + "*"):
                    keys.add(str(key))
            except Exception as e:
                await self._conn.mark_failure(e)
                raise StoreUnavailable("zone registry") from e

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
        'memory' when no Redis is configured: governance writes then live in ONE worker and die with it, and the CRUD API reports it so the Studio can warn.
        With Redis configured and down a write raises.
        """
        return "memory" if self._in_memory() else "redis"

    async def _delete_key(self, key: str) -> bool:
        if self._in_memory():
            return self._memory.pop(key, None) is not None
        redis = await self._conn.get()
        if redis is None:
            raise StoreUnavailable("zone registry")
        try:
            existed = bool(await redis.delete(key))
        except Exception as e:
            await self._conn.mark_failure(e)
            raise StoreUnavailable("zone registry") from e
        self._memory[key] = None
        return existed


def _parse(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """A stored record, or None; a corrupt entry is no config and the next write replaces it."""
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _version(main: Optional[Dict[str, Any]], draft: Optional[Dict[str, Any]]) -> int:
    return max(main["version"] if main else 0, draft["version"] if draft else 0)


def _check_version(expected: Optional[int], current: int, action: str) -> None:
    if expected is not None and expected != current:
        raise VersionConflict(
            f"expected version {expected}, but the latest is {current}: "
            f"reload before {action}"
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
