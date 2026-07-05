"""
Events API
Ingestion of UI events (impressions, clicks) emitted by GenUI zones,
closing the measurement loop: every generated variant can be tied to
what users actually did with it.

- POST /api/v1/events       (client key)  : batch event ingestion
- GET  /api/v1/events/stats (admin key)   : per-arm CTR and uplift

Counters are aggregated per (tenant, zone, experiment arm) in the
metrics store; each raw event also lands in the audit log for offline
analysis (per segment, per item, per time window).
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from auth import AuthContext
from auth.dependencies import get_audit_logger, require_admin, require_client
from config import settings
from metrics import MetricsStore
from metrics.store import COUNTED_EVENTS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])

MAX_EVENTS_PER_BATCH = 100


# Models
class UIEvent(BaseModel):
    """A single UI event emitted by a GenUI zone."""
    event_type: str = Field(
        ...,
        pattern="^[a-z_]{1,32}$",
        description="impression | click | custom snake_case types (e.g. conversion)"
    )
    zone_id: str = Field(..., max_length=128)
    render_id: Optional[str] = Field(
        None, max_length=64,
        description="Identity of the generated variant (from meta.render_id)"
    )
    arm: Optional[str] = Field(
        None, pattern="^(personalized|control|none)$",
        description="Experiment arm (from meta.experiment.arm)"
    )
    segment: Optional[str] = Field(None, max_length=200)
    item_title: Optional[str] = Field(None, max_length=300)
    item_url: Optional[str] = Field(None, max_length=2000)
    user_id: Optional[str] = Field(None, max_length=128)
    ts: Optional[str] = Field(None, description="Client timestamp (ISO 8601)")


class EventBatch(BaseModel):
    """Batch of UI events."""
    events: List[UIEvent] = Field(..., min_length=1, max_length=MAX_EVENTS_PER_BATCH)


# Singleton
_metrics_store: Optional[MetricsStore] = None


def get_metrics_store() -> MetricsStore:
    """Get or create the metrics store singleton."""
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore(redis_url=settings.redis_url)
    return _metrics_store


# Endpoints
@router.post("")
async def ingest_events(
    batch: EventBatch,
    auth: AuthContext = Depends(require_client),
):
    """
    Ingest a batch of UI events.

    impression/click events update the per-arm counters used for uplift
    computation; every event is also appended to the audit log.
    """
    metrics = get_metrics_store()
    audit = get_audit_logger()

    counted = 0
    for event in batch.events:
        arm = event.arm or "none"

        if event.event_type in COUNTED_EVENTS:
            try:
                await metrics.record(auth.tenant, event.zone_id, arm, event.event_type)
                counted += 1
            except Exception as e:
                logger.warning("Metrics record failed: %s", e)

        audit.log(
            f"ui_{event.event_type}",
            tenant=auth.tenant,
            user_id=event.user_id,
            key=auth.key_fingerprint,
            zone_id=event.zone_id,
            render_id=event.render_id,
            arm=arm,
            segment=event.segment,
            item_title=event.item_title,
            item_url=event.item_url,
            client_ts=event.ts,
        )

    return {
        "status": "accepted",
        "received": len(batch.events),
        "counted": counted,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def event_stats(
    zone_id: str = Query(..., description="Zone to compute stats for"),
    auth: AuthContext = Depends(require_admin),
):
    """
    Per-arm impression/click counters, CTR, and personalization uplift
    for a zone (admin only).

    uplift_percent = (ctr_personalized - ctr_control) / ctr_control * 100
    """
    metrics = get_metrics_store()
    stats = await metrics.stats(auth.tenant, zone_id)
    stats["holdout_percent"] = settings.holdout_percent
    return stats
