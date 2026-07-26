"""
Zone Config Governance API
List a tenant's zones, edit a draft, preview it (via preview_draft on /zone/render), approve it.

Every route requires an admin key; the tenant always comes from the
key, never from the request.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from api.deps import get_zone_config_store
from api.zone_router import PinnedContent
from auth import AuthContext
from auth.dependencies import get_audit_logger, require_admin
from zones import STATUS_APPROVED, STATUS_DRAFT, VersionConflict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zone/config", tags=["zone-config"])

_ZONE_ID = Path(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class ZoneConfigWrite(BaseModel):
    """The governed block as the editor submits it, validated at the API
    boundary (typed pinned content, bounded constraints)."""

    model_config = {"extra": "forbid"}

    base_prompt: str = "Show relevant content for this user"
    context_prompt: Optional[str] = None
    pinned_content: List[PinnedContent] = Field(default_factory=list)
    preferred_component_type: Optional[str] = None
    max_items: int = Field(default=6, ge=1)
    max_components: Optional[int] = Field(default=None, ge=1, le=10)
    expected_version: Optional[int] = Field(
        None,
        description="Optimistic concurrency: the latest version you loaded; "
                    "409 when someone else edited in the meantime",
    )

    def config_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude={"expected_version"})


class ApproveBody(BaseModel):
    expected_version: Optional[int] = None


def _audit_change(
    auth: AuthContext, zone_id: str, action: str, version: Optional[int] = None
) -> None:
    """Every governance state transition on the same audit trail as renders."""
    get_audit_logger().log(
        "zone_config_change",
        tenant=auth.tenant,
        key=auth.key_fingerprint,
        zone_id=zone_id,
        action=action,
        version=version,
    )


@router.get("")
async def list_zone_configs(auth: AuthContext = Depends(require_admin)):
    """
    Every zone of this tenant: the union of registry entries and zones
    the site actually rendered, each tagged ungoverned | draft | approved.
    """
    store = get_zone_config_store()
    governed = await store.list_zones(auth.tenant)
    observed = await store.observed(auth.tenant)

    zones = []
    for zone_id in sorted(set(governed) | observed):
        entry = governed.get(zone_id)
        zones.append({
            "zone_id": zone_id,
            "status": entry["status"] if entry else "ungoverned",
            "version": entry["version"] if entry else None,
            "updated_at": entry["updated_at"] if entry else None,
            "has_draft": entry["has_draft"] if entry else False,
            "observed": zone_id in observed,
        })

    return {"zones": zones, "storage": await store.storage_backend()}


@router.get("/{zone_id}")
async def get_zone_config(
    zone_id: str = _ZONE_ID,
    auth: AuthContext = Depends(require_admin),
):
    """Both slots of one zone, for the editor: approved and draft."""
    store = get_zone_config_store()
    main = await store.get(auth.tenant, zone_id)
    draft = await store.get_draft(auth.tenant, zone_id)
    if draft is None and main is not None and main.get("status") == STATUS_DRAFT:
        draft, main = main, None  # phase-1 drafts lived in the main slot

    return {
        "zone_id": zone_id,
        "approved": main if main and main.get("status") == STATUS_APPROVED else None,
        "draft": draft,
        "observed": zone_id in await store.observed(auth.tenant),
    }


@router.put("/{zone_id}")
async def save_zone_draft(
    body: ZoneConfigWrite, 
    zone_id: str = _ZONE_ID,
    auth: AuthContext = Depends(require_admin),
):
    """Save an edit as the zone's DRAFT. Production is untouched until approve."""
    store = get_zone_config_store()
    try:
        record = await store.save_draft(
            auth.tenant, zone_id, body.config_dict(), body.expected_version
        )
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))

    _audit_change(auth, zone_id, "draft_saved", record["version"])
    return {
        "zone_id": zone_id,
        "record": record,
        "storage": await store.storage_backend(),
    }


@router.post("/{zone_id}/approve")
async def approve_zone_config(
    zone_id: str = _ZONE_ID,
    body: Optional[ApproveBody] = None,
    auth: AuthContext = Depends(require_admin),
):
    """
    Promote the draft to APPROVED: from this response on, every render of
    (tenant, zone_id) serves exactly this config (host props ignored),
    and the cache invalidates itself because the config feeds its key.
    """
    store = get_zone_config_store()
    try:
        record = await store.approve(
            auth.tenant, zone_id, body.expected_version if body else None
        )
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"No draft to approve for zone '{zone_id}'"
        )

    _audit_change(auth, zone_id, "approved", record["version"])
    return {
        "zone_id": zone_id,
        "record": record,
        "storage": await store.storage_backend(),
    }


@router.delete("/{zone_id}/draft")
async def discard_zone_draft(
    zone_id: str = _ZONE_ID,
    auth: AuthContext = Depends(require_admin),
):
    """Drop the draft; the approved record keeps serving unchanged."""
    store = get_zone_config_store()
    if not await store.discard_draft(auth.tenant, zone_id):
        raise HTTPException(
            status_code=404, detail=f"No draft for zone '{zone_id}'"
        )
    _audit_change(auth, zone_id, "draft_discarded")
    return {"zone_id": zone_id, "discarded": True}


@router.delete("/{zone_id}")
async def delete_zone_config(
    zone_id: str = _ZONE_ID,
    auth: AuthContext = Depends(require_admin),
):
    """Remove the whole registry entry: the zone goes back to host props."""
    store = get_zone_config_store()
    if not await store.delete(auth.tenant, zone_id):
        raise HTTPException(
            status_code=404, detail=f"No registry entry for zone '{zone_id}'"
        )
    _audit_change(auth, zone_id, "deleted")
    return {"zone_id": zone_id, "deleted": True}
