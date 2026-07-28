"""
AI content disclosure: the marking that travels WITH the content.

Two facts are recorded about every payload the backend serves:

- ai_generated: did a model actually write any of this? A render
  assembled from the operator's own pinned content after a generation
  failure did not, and saying otherwise would be a false marking.
- provenance: when a model did run, is the visible text original prose
  ("generated") or is every displayed string a verbatim copy of the
  operator's input ("verbatim-from-input")?

The provenance value is EVIDENCE, not an exemption. A zone whose every
URL and every number comes from the input can still be pure synthetic
prose: the guards only prove nothing was invented in those two
dimensions, never that the wording is the operator's. So the value is
"verbatim-from-input" only when every visible string is found verbatim
in the input corpus, and "generated" in every other case, including
every case where the comparison cannot be made with certainty.

Known limits of the comparison (deliberate, they all fail towards
"generated"): matching is substring-based on lowercased, whitespace
collapsed text, so a string the model reflowed or re-punctuated counts
as generated, and so does a quoted string whose input copy lives inside
a JSON-encoded field.

No cryptographic signature is produced here. C2PA 2.4 can carry a
manifest in HTML and defines a c2pa.ai-disclosure assertion, but a
manifest is only worth what its certificate chain is worth: it needs a
signing identity, key custody and a revocation story that belong to the
operator's infrastructure, not to a library that ships as source. The
marking below is unsigned and therefore strippable by anyone who
controls the response; it is a declaration, not a proof. The block is
shaped so a signature can be attached to it later without moving it.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# A model wrote original text.
PROVENANCE_GENERATED = "generated"
# A model ran, but every visible string is a verbatim copy of the input.
PROVENANCE_VERBATIM = "verbatim-from-input"
# No model output is being served (fallback assembled from operator content).
PROVENANCE_NONE = "not-generated"

# What produced the content, for a reader of the raw payload. The model
# name is deliberately NOT part of it by default: see disclosure_block.
SYSTEM_NAME = "genui"


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace: the only tolerance we allow."""
    return " ".join(str(text).lower().split())


def _collect_strings(node: Any, out: List[str]) -> None:
    """Every string a component carries, at any depth."""
    if isinstance(node, str):
        if node.strip():
            out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            _collect_strings(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_strings(item, out)


def content_provenance(components: List[Dict[str, Any]], corpus: str) -> str:
    """
    Decide whether the visible content is original prose or the input.

    Only the `data` of each component is examined: `layout` carries
    structural hints the visitor never reads. An empty render proves
    nothing, so it stays "generated".
    """
    strings: List[str] = []
    for component in components or []:
        _collect_strings(component.get("data"), strings)

    if not strings:
        return PROVENANCE_GENERATED

    haystack = _normalize(corpus or "")
    for value in strings:
        if _normalize(value) not in haystack:
            return PROVENANCE_GENERATED
    return PROVENANCE_VERBATIM


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def disclosure_block(
    ai_generated: bool,
    provenance: str,
    generated_at: Optional[str] = None,
    model: Optional[str] = None,
    enabled: bool = True,
    expose_model: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Build the disclosure block, or None when the operator turned it off.

    generated_at is the moment the content was PRODUCED, never the
    moment it is served: a cached render is shown to a whole segment for
    as long as the stale window lasts, and a serve-time stamp would
    claim a generation that never happened.

    The model name is off by default (DISCLOSURE_EXPOSE_MODEL). What the
    transparency obligation asks is that the reader knows the content is
    artificially generated, not which model wrote it; naming the model
    hands an attacker the exact target to craft prompts against and
    publishes the operator's vendor choice, which is theirs to disclose.
    """
    if not enabled:
        return None

    block: Dict[str, Any] = {
        "ai_generated": bool(ai_generated),
        "provenance": provenance if ai_generated else PROVENANCE_NONE,
        "generated_at": generated_at or utc_now_iso(),
        "system": SYSTEM_NAME,
    }
    if expose_model and model:
        block["model"] = model
    return block
