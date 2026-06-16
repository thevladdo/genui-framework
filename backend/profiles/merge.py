"""
Profile Merge Module
Pure merge logic for user profiles.

Profile shape (sections of {key: entry} maps):
    {
        "preferences": {"role": {"value": "developer", "confidence": 0.9, "updated_at": ...}},
        "interests":   {...},
        "demographic": {...},
        "behavior":    {...},
    }

Merge rule everywhere: an entry is overwritten only by a value with
strictly higher confidence (mirrors ProfileAgent.merge_profile_updates,
so server-side and agent-side merging stay consistent).
"""

import time
from typing import Any, Dict, List, Optional

PROFILE_SECTIONS = ("preferences", "interests", "demographic", "behavior", "context")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _entry_confidence(entry: Any) -> float:
    if isinstance(entry, dict):
        try:
            return float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def apply_profile_updates(
    profile: Optional[Dict[str, Any]],
    updates: List[Dict[str, Any]],
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Apply agent-produced updates ({"field": "section.key", "value", "confidence"})
    to a profile. Higher confidence wins; malformed updates are skipped.

    Returns a new profile dict (the input is not mutated).
    """
    result: Dict[str, Any] = {k: dict(v) if isinstance(v, dict) else v for k, v in (profile or {}).items()}
    ts = timestamp or _now_iso()

    for update in updates or []:
        if not isinstance(update, dict):
            continue
        field = str(update.get("field", ""))
        parts = field.split(".")
        if len(parts) != 2 or not all(parts):
            continue
        section, key = parts
        value = update.get("value")
        if value is None:
            continue
        try:
            confidence = float(update.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        bucket = result.setdefault(section, {})
        if not isinstance(bucket, dict):
            continue

        existing = bucket.get(key)
        if existing is None or confidence > _entry_confidence(existing):
            bucket[key] = {
                "value": value,
                "confidence": confidence,
                "updated_at": ts,
            }

    return result


def merge_client_profile(
    server_profile: Optional[Dict[str, Any]],
    client_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merge a client-side (IndexedDB) profile into the server profile.

    Used during migration/sync: the server copy is authoritative, but a
    client entry with strictly higher confidence (e.g. collected while
    the server had no data) is taken over. Non-entry values and unknown
    sections from the server are preserved as-is.
    """
    result: Dict[str, Any] = {k: dict(v) if isinstance(v, dict) else v for k, v in (server_profile or {}).items()}

    for section, entries in (client_profile or {}).items():
        if not isinstance(entries, dict):
            # Scalar fields (userId, history_summary, ...): only fill gaps
            result.setdefault(section, entries)
            continue

        bucket = result.setdefault(section, {})
        if not isinstance(bucket, dict):
            continue

        for key, entry in entries.items():
            existing = bucket.get(key)
            if existing is None:
                bucket[key] = entry
            elif _entry_confidence(entry) > _entry_confidence(existing):
                bucket[key] = entry

    return result
