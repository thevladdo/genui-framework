"""
Tenant Theme API
Read/write of the per-tenant theme the Studio Playground now saves
(utils/theme_store).
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import AuthContext
from auth.dependencies import get_audit_logger, require_admin, require_client
from utils.theme_store import TenantTheme, get_theme_store

router = APIRouter(prefix="/api/v1/theme", tags=["theme"])


class ThemeWrite(BaseModel):
    model_config = {"extra": "forbid"}

    theme: TenantTheme


@router.get("")
async def get_theme(auth: AuthContext = Depends(require_client)):
    """
    This tenant's saved theme, or nulls when none was ever saved.

    Callers must handle theme=null: no saved theme means the library
    defaults apply, which is exactly what an unthemed host renders today.
    """
    record: Optional[dict] = await get_theme_store().get(auth.tenant)
    return {
        "theme": record["theme"] if record else None,
        "updated_at": record["updated_at"] if record else None,
    }


@router.put("")
async def set_theme(
    body: ThemeWrite,
    auth: AuthContext = Depends(require_admin),
):
    """
    Replace this tenant's saved theme. Served by GET from the next call on;
    hosts that fetch the theme at boot pick it up on their next boot. The
    change is audit-logged on the same trail as renders.
    """
    store = get_theme_store()
    record = await store.set(auth.tenant, body.theme)
    get_audit_logger().log(
        "theme_change",
        tenant=auth.tenant,
        key=auth.key_fingerprint,
        action="saved",
        token_count=len(record["theme"]),
    )
    return {**record, "storage": await store.storage_backend()}
