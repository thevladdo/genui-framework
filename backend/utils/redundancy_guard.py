"""
Redundancy Guard

A zone is read top to bottom as ONE band, but the model writes it in one
shot: nothing stops it from spending its second component repeating the
first one's link under the first one's wording. The observed shape is a
hero with two CTAs pointing at the same URL, followed by a full-width
card whose only content is that same link and that same label again.
Three elements, one piece of information.

The prompt asks for non-redundancy (rule 11), and like every other
guarantee in this chain that instruction is not the guarantee: this
module enforces the part that can be decided deterministically.

Enforced scope:
- the SAME link target twice inside one component (a hero's second CTA
  pointing where the first already points) -> the later one is removed;
- the same target AND the same wording as an element of an EARLIER
  component -> removed, because it carries no information the visitor
  has not just read;
- a component whose item list is emptied by the above is dropped whole
  (the same rule the URL guard already applies to an empty buttons
  component).

Removals are reported into meta.sanitization.dropped_components, the
same list the schema and budget steps use, so the Studio preview and the
audit trail show them with no new field.
"""

from typing import Any, Dict, List, Optional, Tuple

from utils.url_guard import normalize_url

_LINK_KEYS = ("url", "link", "href")
_LABEL_KEYS = ("label", "title", "name", "alt", "headline", "heading")


def _text(node: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _action_of(node: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """(target, wording) when this dict is a link the visitor can click."""
    url = _text(node, _LINK_KEYS)
    if url is None:
        return None
    label = _text(node, _LABEL_KEYS) or ""
    return normalize_url(url), " ".join(label.lower().split())


class RedundancyGuard:
    """
    Stateful across the components of ONE render.

    Statefulness is what makes "the second component must consider the
    first" enforceable, and it is also what makes the streaming path work
    for free: components arrive one at a time and the guard remembers
    what the visitor has already been shown.
    """

    def __init__(self, enforce: bool = True):
        self.enforce = enforce
        self._seen: Dict[str, str] = {}

    def sanitize_components(
        self,
        components: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Drop redundant links (and the components they empty).

        Returns:
            (kept_components, dropped_notes)
        """
        if not self.enforce:
            return components, []

        kept: List[Dict[str, Any]] = []
        notes: List[str] = []

        for component in components:
            ctype = str(component.get("type", "component"))
            data = component.get("data")
            if not isinstance(data, dict):
                kept.append(component)
                continue

            filled_lists = [
                key
                for key, value in data.items()
                if isinstance(value, list) and value
            ]
            within: Dict[str, str] = {}
            mark = len(notes)
            self._prune(data, within, notes, ctype)

            if any(not data.get(key) for key in filled_lists):
                del notes[mark:]
                notes.append(
                    f"{ctype}: everything in it repeated content already shown above"
                )
                continue

            for target, label in within.items():
                self._seen.setdefault(target, label)
            kept.append(component)

        return kept, notes

    def _prune(
        self,
        node: Any,
        within: Dict[str, str],
        notes: List[str],
        ctype: str,
    ) -> Any:
        """Walk one component's data, returning None for a removed node."""
        if isinstance(node, list):
            out = []
            for item in node:
                pruned = self._prune(item, within, notes, ctype)
                if pruned is not None:
                    out.append(pruned)
            return out

        if not isinstance(node, dict):
            return node

        action = _action_of(node)
        if action is not None:
            target, label = action
            if target in within:
                notes.append(f"{ctype}: second link to {target} in the same component")
                return None
            if self._seen.get(target) == label:
                notes.append(
                    f"{ctype}: repeats '{label}' -> {target} from an earlier component"
                )
                return None
            within[target] = label

        for key in list(node.keys()):
            value = node[key]
            if isinstance(value, (dict, list)):
                pruned = self._prune(value, within, notes, ctype)
                if pruned is None:
                    node.pop(key)
                else:
                    node[key] = pruned

        return node
