"""
Per-Tenant Content Policy

Post-generation enforcement of tenant-configured banned terms, applied
as a step of the guarantee chain (validate -> URL guard -> numeric
grounding -> content policy -> pinned). A regulated tenant (insurance,
finance, pharma) can guarantee that specific terms never reach the page,
whatever the model emits:

- a component containing a banned term anywhere in its data is DROPPED
  whole (redacting a card about a banned topic still shows the topic);
- the chat text_response gets the term REDACTED (dropping the whole
  answer over one word would break the conversation);
- every hit is reported in meta.sanitization.policy_violations.

Tone constraints are deliberately NOT here: a regex cannot verify tone.
Tone stays a prompt-level instruction (best-effort), and the contract
documents it as such.

Configuration: the CONTENT_POLICY env var holds a JSON object mapping
tenant -> policy; "*" applies to every tenant and merges with the
tenant-specific entry:

    CONTENT_POLICY={"*": {"banned_terms": ["free money"]},
                    "acme": {"banned_terms": ["guaranteed returns"]}}

Invalid configuration raises ContentPolicyError: a typo must fail loudly
(renders degrade to the pinned-only fallback), never silently disable a
compliance feature.
"""

import json
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

REDACTION_MARK = "[removed]"


class ContentPolicyError(ValueError):
    """CONTENT_POLICY is misconfigured; the message says how to fix it."""


class ContentPolicy:
    """Banned-term matcher: case-insensitive, word-boundary, phrase-aware."""

    def __init__(self, banned_terms: Iterable[str]):
        self.banned_terms = [str(t).strip() for t in banned_terms if str(t).strip()]
        self._patterns = [
            # (?<!\w)/(?!\w) instead of \b: correct also for terms that
            # start or end with a non-word character
            (term, re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE))
            for term in self.banned_terms
        ]

    def __bool__(self) -> bool:
        return bool(self._patterns)

    def matches(self, text: Optional[Any]) -> List[str]:
        """Banned terms present in a text value."""
        if not text:
            return []
        value = str(text)
        return [term for term, pattern in self._patterns if pattern.search(value)]

    def _scan(self, node: Any) -> List[str]:
        if isinstance(node, str):
            return self.matches(node)
        if isinstance(node, dict):
            return [t for value in node.values() for t in self._scan(value)]
        if isinstance(node, list):
            return [t for item in node for t in self._scan(item)]
        return []

    def sanitize_components(
        self, components: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Drop every component containing a banned term; report the terms."""
        if not self._patterns:
            return components, []
        kept: List[Dict[str, Any]] = []
        violations: List[str] = []
        for component in components:
            hits = self._scan(component.get("data"))
            if hits:
                violations.extend(dict.fromkeys(hits))
            else:
                kept.append(component)
        return kept, violations

    def redact(self, text: Optional[str]) -> Tuple[str, List[str]]:
        """Replace banned terms in free text (chat prose) with a marker."""
        if not text or not self._patterns:
            return text or "", []
        matched: List[str] = []
        for term, pattern in self._patterns:
            if pattern.search(text):
                matched.append(term)
                text = pattern.sub(REDACTION_MARK, text)
        return text, matched


@lru_cache(maxsize=8)
def _parse_config(raw: str) -> Dict[str, Tuple[str, ...]]:
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ContentPolicyError(
            f"CONTENT_POLICY is not valid JSON: {e}. Expected an object like "
            '{"*": {"banned_terms": ["term"]}, "<tenant>": {"banned_terms": [...]}}'
        )
    if not isinstance(data, dict):
        raise ContentPolicyError("CONTENT_POLICY must be a JSON object keyed by tenant")
    policies: Dict[str, Tuple[str, ...]] = {}
    for tenant, config in data.items():
        terms = config.get("banned_terms", []) if isinstance(config, dict) else None
        if not isinstance(terms, list):
            raise ContentPolicyError(
                f"CONTENT_POLICY entry for {tenant!r} must be an object with a "
                f"'banned_terms' list"
            )
        policies[str(tenant)] = tuple(str(t) for t in terms)
    return policies


def policy_for(tenant: Optional[str], raw: str) -> ContentPolicy:
    """
    The effective policy for a tenant: "*" terms plus tenant terms.

    `raw` is the CONTENT_POLICY setting; callers pass it explicitly so
    this module stays pure (importable and testable without app config).
    """
    config = _parse_config(raw or "")
    terms = list(config.get("*", ())) + list(config.get(tenant or "default", ()))
    return ContentPolicy(terms)
