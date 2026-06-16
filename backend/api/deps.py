"""
Shared service singletons for API routers.
"""

from typing import Optional

from config import settings
from profiles import ProfileStore

_profile_store: Optional[ProfileStore] = None


def get_profile_store() -> ProfileStore:
    """Get or create the server-side profile store singleton."""
    global _profile_store
    if _profile_store is None:
        _profile_store = ProfileStore(
            redis_url=settings.redis_url,
            ttl_seconds=settings.profile_ttl_seconds,
        )
    return _profile_store
