"""
Audit Query API
Read path over the append-only audit trail: "what was shown to whom",
queryable per tenant/user/zone/date instead of a grep on server disks.

The source is abstracted (auth.dependencies.get_audit_reader): the
single-worker file sink is queryable here; the production default
(logger sink, host log pipeline) is reported as queryable=false with a
note, never as a silent empty result.

Admin only; the tenant always comes from the key, never from the query.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import AuthContext
from auth.dependencies import get_audit_reader, require_admin

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
_DATE = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


@router.get("")
def query_audit(
    auth: AuthContext = Depends(require_admin),
    user_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    event: Optional[str] = None,
    date_from: Optional[str] = _DATE,
    date_to: Optional[str] = _DATE,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Query this tenant's audit trail, newest first.

    Answers the compliance question "what did user X see on day Z":
    every served render (segment, cache state, shown titles and links,
    what the guarantee chain removed) plus profile/document/governance
    events, filtered by user, zone, event type and date range.
    """
    reader = get_audit_reader()
    result = reader.query(
        auth.tenant,
        user_id=user_id,
        zone_id=zone_id,
        event=event,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {
        "source": reader.source,
        "queryable": reader.queryable,
        "note": reader.note,
        **result,
    }
