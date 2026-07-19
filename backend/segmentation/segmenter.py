"""
Profile Segmenter Module
Maps a user profile + behavior data to a deterministic, human-readable
segment key.

The segmenter is the foundation of the zone render cache: instead of
calling the LLM once per user per request, zone renders are computed
once per *segment* and shared by every user that falls into it.

Design constraints:
- Deterministic: same inputs always produce the same key (no LLM, no time).
- Coarse on purpose: a handful of dimensions (role, top interests, browsing style, engagement) so that most traffic collapses into a
  small number of segments. Users with no signals share the "anon" segment, which is typically the most-hit cache entry.
- Readable: keys like "role=developer|int=ai+sustainability|eng=high" can be logged, inspected in the debug panel, and used to pre-warm the cache for known archetypes.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Segment key for users with no usable signals
ANONYMOUS_SEGMENT = "anon"

_SLUG_MAX_LENGTH = 24
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class Segment:
    """A computed user segment."""
    key: str
    factors: List[str] = field(default_factory=list)

    @property
    def is_anonymous(self) -> bool:
        return self.key == ANONYMOUS_SEGMENT

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "factors": self.factors}


def _slugify(value: Any) -> str:
    """Normalize a value into a short, key-safe slug."""
    slug = _SLUG_PATTERN.sub("-", str(value).strip().lower()).strip("-")
    return slug[:_SLUG_MAX_LENGTH]


def _entry_value(entry: Any) -> Any:
    """Unwrap the {"value": ..., "confidence": ...} profile entry shape."""
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


def _entry_confidence(entry: Any) -> float:
    """Confidence of a profile entry; bare values count as fully confident."""
    if isinstance(entry, dict) and "value" in entry:
        try:
            return float(entry.get("confidence", 1.0))
        except (TypeError, ValueError):
            return 0.0
    return 1.0


def _extract_role(
    user_profile: Dict[str, Any],
    min_confidence: float,
) -> Optional[str]:
    """Role from preferences or demographics, whichever is confident first."""
    for section_name in ("preferences", "demographic"):
        section = user_profile.get(section_name)
        if not isinstance(section, dict):
            continue
        entry = section.get("role")
        if entry is None:
            continue
        if _entry_confidence(entry) < min_confidence:
            continue
        value = _entry_value(entry)
        if value:
            return _slugify(value)
    return None


def _extract_interests(
    user_profile: Dict[str, Any],
    min_confidence: float,
    max_interests: int,
) -> List[str]:
    """
    Confident interests, alphabetically sorted and capped.

    Interests appear in two shapes in practice:
    - {"sustainability": {"value": true, ...}} -> the key is the interest
    - {"products": {"value": "trains", ...}}   -> the value is the interest
    """
    interests = user_profile.get("interests")
    if not isinstance(interests, dict):
        return []

    extracted = set()
    for key, entry in interests.items():
        if _entry_confidence(entry) < min_confidence:
            continue
        value = _entry_value(entry)
        if value is None or value is False:
            continue
        if value is True:
            extracted.add(_slugify(key))
        elif isinstance(value, str) and value.strip():
            extracted.add(_slugify(value))
        else:
            extracted.add(_slugify(key))

    return sorted(extracted)[:max_interests]


def _extract_user_type(
    user_profile: Dict[str, Any],
    behavior_data: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Browsing style, from live behavior data or the stored profile."""
    if behavior_data and behavior_data.get("userType"):
        return _slugify(behavior_data["userType"])

    behavior = user_profile.get("behavior")
    if isinstance(behavior, dict):
        stored = behavior.get("_user_type")
        stored_value = _entry_value(stored) if stored is not None else None
        if stored_value:
            return _slugify(stored_value)
    return None


def _extract_engagement(behavior_data: Optional[Dict[str, Any]]) -> Optional[str]:
    """Bucket engagement into low/mid/high from scroll depth."""
    if not behavior_data:
        return None
    depth = behavior_data.get("maxScrollDepth")
    if not isinstance(depth, (int, float)):
        return None
    if depth >= 70:
        return "high"
    if depth >= 30:
        return "mid"
    return "low"


# Segment-key prefixes -> archetype field names
_ARCHETYPE_FIELDS = {
    "role": "role",
    "int": "interests",
    "type": "user_type",
    "eng": "engagement",
}


def segment_archetype(segment: Segment) -> Dict[str, Any]:
    """
    Parse a segment key back into its canonical audience archetype.

    The archetype is the ONLY user-derived input allowed into the prompt
    of a shared (cached) render. It is parsed from the KEY itself — not
    from the profile that produced it — so the prompt input of a cached
    render is a pure function of its cache key: whatever the first
    requester of a segment put in their raw profile cannot reach a
    render served to everyone else. Values are slugs by construction
    ([a-z0-9-], length- and count-capped at segmentation time).
    """
    if segment.is_anonymous:
        return {}

    archetype: Dict[str, Any] = {}
    for part in segment.key.split("|"):
        prefix, _, value = part.partition("=")
        name = _ARCHETYPE_FIELDS.get(prefix)
        if not name or not value:
            continue
        archetype[name] = value.split("+") if name == "interests" else value
    return archetype


def compute_segment(
    user_profile: Optional[Dict[str, Any]],
    behavior_data: Optional[Dict[str, Any]] = None,
    min_confidence: float = 0.5,
    max_interests: int = 3,
) -> Segment:
    """
    Compute the cache segment for a user.

    Args:
        user_profile: Profile in the API format (preferences/interests/
            demographic/behavior with {"value", "confidence"} entries).
        behavior_data: Compact behavior summary from the BehaviorTracker.
        min_confidence: Entries below this confidence are ignored, so
            low-confidence guesses don't fragment the cache.
        max_interests: Cap on interest dimensions to bound segment count.

    Returns:
        Segment with a deterministic key and the factors that shaped it.
        Users with no usable signals share the ANONYMOUS_SEGMENT.
    """
    profile = user_profile if isinstance(user_profile, dict) else {}

    parts: List[str] = []
    factors: List[str] = []

    role = _extract_role(profile, min_confidence)
    if role:
        parts.append(f"role={role}")
        factors.append("role")

    interests = _extract_interests(profile, min_confidence, max_interests)
    if interests:
        parts.append(f"int={'+'.join(interests)}")
        factors.append("interests")

    user_type = _extract_user_type(profile, behavior_data)
    if user_type:
        parts.append(f"type={user_type}")
        factors.append("user_type")

    engagement = _extract_engagement(behavior_data)
    if engagement:
        parts.append(f"eng={engagement}")
        factors.append("engagement")

    if not parts:
        return Segment(key=ANONYMOUS_SEGMENT, factors=[])

    return Segment(key="|".join(parts), factors=factors)
