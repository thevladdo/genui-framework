"""
What an ingest is doing, and the one flag that stops it.

A large document is thousands of model calls over many minutes, behind a
single request that answers only at the end.

Redis when configured, because the request that starts a run and the one
that stops it are not promised to land on the same worker. 
Entries expire: they describe something in flight, not something configured.
"""

import time
from typing import Any, Dict, Optional

from utils.tenant_json_store import TenantJsonStore

# Long enough to outlive a slow ingest, short enough that nothing lingers
_TTL_SECONDS = 3600

# The id is client-supplied and becomes the key.
_MAX_ID_LENGTH = 64

_STORE: Optional[TenantJsonStore] = None


def _store() -> TenantJsonStore:
    """
    The process-wide store, on the deployment's Redis. Resolved on first use
    so the module imports without app config. Without the URL each worker
    keeps its own copy, and a stop served by another worker never reaches
    the run.
    """
    global _STORE
    if _STORE is None:
        from config import settings

        # A run is not stopped by an outage of its progress record: in flight, not authoritative.
        _STORE = TenantJsonStore(
            key_prefix="genui:ingest:", redis_url=settings.redis_url, authoritative=False
        )
    return _STORE


async def begin(ingest_id: str, total: int, source: str, tenant: str) -> bool:
    """
    Record a run about to start. False when this id was stopped, and the
    caller does no work.

    The same id comes back to carry a run on: the next call of a backfill,
    the second phase of an upload. A stop recorded under it is kept, so the
    loop it was meant to end cannot reopen it; carrying on after a stop
    takes a new id. A stop that lands between the read and the write below
    is lost: the store has no compare-and-set.
    """
    if not ingest_id or len(ingest_id) > _MAX_ID_LENGTH:
        return True
    previous = await _store().get(ingest_id)
    if previous and previous.get("cancelled") and previous.get("tenant") == tenant:
        return False
    await _store().set(ingest_id, {
        "phase": "contextualizing" if total else "indexing",
        "source": source,
        "tenant": tenant,
        "total": total,
        "done": 0,
        "cancelled": False,
        "started_at": time.time(),
    }, ttl_seconds=_TTL_SECONDS)
    return True


async def advance(ingest_id: str, done: int, phase: Optional[str] = None) -> bool:
    """
    Record progress and report whether the run should carry on.

    False means someone asked it to stop, and the caller is expected to
    leave what it has already written where it is.
    """
    if not ingest_id:
        return True
    status = await _store().get(ingest_id)
    if not status:
        return True
    
    status["done"] = done
    if phase:
        status["phase"] = phase
    await _store().set(ingest_id, status, ttl_seconds=_TTL_SECONDS)
    return not status.get("cancelled")


async def cancelled(ingest_id: str) -> bool:
    """
    Whether a stop has been asked for. Reads, never writes.

    The run asks this once per chunk, from several coroutines at a time.
    `advance` reads the record, edits it and writes it back, so asking it
    that often would eventually put a stale copy back over a flag that
    arrived in between, and the stop would be lost exactly when it was
    pressed. Progress is written at batch boundaries, where there is one
    writer; this one only looks.
    """
    if not ingest_id:
        return False
    status = await _store().get(ingest_id)
    return bool(status and status.get("cancelled"))


async def finish(ingest_id: str, phase: str = "done") -> None:
    """Mark a run over, so a poller stops asking."""
    if not ingest_id:
        return
    status = await _store().get(ingest_id) or {}
    status["phase"] = phase
    status["finished_at"] = time.time()
    await _store().set(ingest_id, status, ttl_seconds=_TTL_SECONDS)


async def cancel(ingest_id: str, tenant: str) -> bool:
    """
    Ask a run to stop. True when there was one of this tenant's to ask.

    The flag is set, not acted on: the run notices between batches, which
    is the only point where stopping leaves a state that can be stated.
    """
    status = await read(ingest_id, tenant)
    if not status:
        return False
    status["cancelled"] = True
    await _store().set(ingest_id, status, ttl_seconds=_TTL_SECONDS)
    return True


async def read(ingest_id: str, tenant: str) -> Optional[Dict[str, Any]]:
    """
    The run's state, for whoever is watching it, scoped to its tenant.

    The id comes from the client and is the whole key, so without this a
    holder of one tenant's admin key could watch or stop another tenant's
    run by knowing its id. Every other boundary in this codebase is drawn
    the same way and this one is not the exception.
    """
    if not ingest_id or len(ingest_id) > _MAX_ID_LENGTH:
        return None
    status = await _store().get(ingest_id)
    if not status or status.get("tenant") != tenant:
        return None
    return status
