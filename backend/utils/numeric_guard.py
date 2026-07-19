"""
Numeric Grounding Guard

"Never invent numbers" in the prompt is an instruction, not a guarantee.
This module enforces it the way the URL guard enforces links: after
generation, every number displayed AS the content must trace back to a
number present in the input (pinned content, developer prompts, RAG
documents, page context). Ungrounded numbers are removed and reported
in meta.sanitization.removed_numbers.

Enforced scope (fields whose value IS a numeric claim):
- stats_banner: each stat's `value` (an ungrounded stat is removed;
  a banner left empty is dropped)
- pricing_cards: each plan's `price` (an ungrounded plan is removed;
  a grid left empty is dropped)
- chart: each data point's `value` (one ungrounded point drops the
  WHOLE chart: a series missing one bar misleads)

Honest limits (documented, never promised as more):
- Grounding is verbatim modulo formatting: "1,200", "1200" and 1200.0
  all match each other. Magnitude/unit conversion is NOT attempted:
  "10M" does not trace to "10,000,000" and gets removed. The model is
  instructed to copy figures as they appear in the input.
- Numbers inside prose (descriptions, labels, markdown text) are NOT
  checked: stripping digits from sentences would mangle legitimate
  text. Prose stays best-effort by design.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Digit runs with optional . or , groups: "1,200", "99.9", "3.11.15"
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _canon(token: str) -> Optional[str]:
    """Canonical form of a numeric token ("1,200" -> "1200"), or None."""
    try:
        value = float(token.replace(",", ""))
    except ValueError:
        return None
    return format(value, ".10f").rstrip("0").rstrip(".")


def extract_numbers(text: Optional[Any]) -> Set[str]:
    """
    Canonical numeric tokens present in INPUT text.

    Generous on unparseable runs (a version like "3.11.15" contributes
    its segments): false-grounding is mild, false-dropping mangles the
    render. Output-side extraction (below) has no such fallback for
    parseable tokens.
    """
    numbers: Set[str] = set()
    if text is None:
        return numbers
    for token in _NUMBER_RE.findall(str(text)):
        canon = _canon(token)
        if canon is not None:
            numbers.add(canon)
        else:
            numbers.update(
                c for c in (_canon(part) for part in re.split(r"[.,]", token)) if c
            )
    return numbers


def _output_tokens(text: str) -> List[str]:
    """Canonical tokens a displayed value claims (ALL must be grounded)."""
    tokens: List[str] = []
    for token in _NUMBER_RE.findall(text):
        canon = _canon(token)
        if canon is not None:
            tokens.append(canon)
        else:
            tokens.extend(
                c for c in (_canon(part) for part in re.split(r"[.,]", token)) if c
            )
    return tokens


class NumericGuard:
    """
    Validates displayed numbers against the numbers present in the input.

    Mirrors UrlGuard: build the allowed set from the request input with
    allow_from_text(), then sanitize_components() on the wire-format
    output. `enforce=False` keeps everything (escape hatch, like
    URL_WHITELIST_ENABLED).
    """

    def __init__(self, enforce: bool = True):
        self.enforce = enforce
        self._allowed: Set[str] = set()
        self.removed_numbers: List[str] = []

    def allow_from_text(self, text: Optional[Any]) -> None:
        self._allowed.update(extract_numbers(text))

    def is_grounded(self, value: Any) -> bool:
        """A value with no numeric token makes no numeric claim: grounded."""
        if not self.enforce or value is None:
            return True
        return all(token in self._allowed for token in _output_tokens(str(value)))

    def _check(self, value: Any) -> bool:
        if self.is_grounded(value):
            return True
        self.removed_numbers.append(str(value))
        return False

    def sanitize_components(
        self, components: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Enforce grounding on validated component dicts (wire format)."""
        self.removed_numbers = []
        if not self.enforce:
            return components, []

        kept: List[Dict[str, Any]] = []
        for component in components:
            ctype = component.get("type")
            data = component.get("data", {})
            if ctype == "stats_banner":
                data["stats"] = [
                    s for s in data.get("stats", []) if self._check(s.get("value"))
                ]
                if not data["stats"]:
                    continue
            elif ctype == "pricing_cards":
                data["plans"] = [
                    p for p in data.get("plans", []) if self._check(p.get("price"))
                ]
                if not data["plans"]:
                    continue
            elif ctype == "chart":
                if not all(self._check(p.get("value")) for p in data.get("data", [])):
                    continue
            kept.append(component)
        return kept, list(self.removed_numbers)
