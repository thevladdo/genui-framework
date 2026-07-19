"""
Shared service singletons for API routers.
"""

from typing import Optional

from config import settings
from profiles import ProfileStore
from zones import ZoneConfigStore

_profile_store: Optional[ProfileStore] = None
_zone_config_store: Optional[ZoneConfigStore] = None


def get_profile_store() -> ProfileStore:
    """Get or create the server-side profile store singleton."""
    global _profile_store
    if _profile_store is None:
        _profile_store = ProfileStore(
            redis_url=settings.redis_url,
            ttl_seconds=settings.profile_ttl_seconds,
        )
    return _profile_store


def get_zone_config_store() -> ZoneConfigStore:
    """Get or create the zone config registry singleton."""
    global _zone_config_store
    if _zone_config_store is None:
        _zone_config_store = ZoneConfigStore(redis_url=settings.redis_url)
    return _zone_config_store
