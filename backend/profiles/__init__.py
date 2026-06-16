"""
Server-side user profiles.

The server store is the source of truth; the frontend IndexedDB copy is
a cache. Merge logic lives in profiles.merge (pure, testable), storage
in profiles.store (Redis with in-memory fallback).
"""

from .merge import apply_profile_updates, merge_client_profile
from .store import ProfileStore

__all__ = ["apply_profile_updates", "merge_client_profile", "ProfileStore"]
