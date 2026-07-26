"""
Content Policy API
Admin read/write of the per-tenant banned-term list that the guarantee
chain enforces post-generation (utils/content_policy_store).
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import AuthContext
from auth.dependencies import get_audit_logger, require_admin
from config import settings
from utils.content_policy import policy_for
from utils.content_policy_store import get_content_policy_store

router = APIRouter(prefix="/api/v1/content-policy", tags=["content-policy"])

_MAX_TERMS = 500


class PolicyWrite(BaseModel):
    model_config = {"extra": "forbid"}

    banned_terms: List[str] = Field(default_factory=list, max_length=_MAX_TERMS)


def _payload(tenant: str, banned_terms: List[str], storage: str) -> dict:
    return {
        "banned_terms": banned_terms,
        "env_terms": policy_for(tenant, settings.content_policy).banned_terms,
        "storage": storage,
    }


@router.get("")
async def get_content_policy(auth: AuthContext = Depends(require_admin)):
    """This tenant's editable banned terms, plus the read-only env terms."""
    store = get_content_policy_store()
    return _payload(auth.tenant, await store.get(auth.tenant), await store.storage_backend())


@router.put("")
async def set_content_policy(
    body: PolicyWrite,
    auth: AuthContext = Depends(require_admin),
):
    """
    Replace this tenant's banned terms. Enforced on the NEXT render of
    every zone and every /query for this tenant (no redeploy). The change
    is audit-logged on the same trail as renders.
    """
    store = get_content_policy_store()
    saved = await store.set(auth.tenant, body.banned_terms)
    get_audit_logger().log(
        "content_policy_change",
        tenant=auth.tenant,
        key=auth.key_fingerprint,
        action="updated",
        term_count=len(saved),
    )
    return _payload(auth.tenant, saved, await store.storage_backend())
