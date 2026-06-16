"""
URL Guard Module
Hard guarantee that generated UI only links to URLs that existed in the
input (pinned content, developer prompts, RAG documents, page context).

The LLM is *instructed* not to invent URLs, but instructions are not
guarantees. This module enforces the rule after generation:

- Dangerous schemes (javascript:, data:, vbscript:, file:) are always
  removed, whitelist enabled or not.
- With the whitelist enabled (default), any URL not present in the input
  is stripped: cards lose their invented link/image, buttons without a
  surviving URL are dropped, markdown links collapse to their text.

Everything removed is reported so it can surface in debug metadata.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Absolute URLs (http/https) — captures until whitespace or closing delimiter
_ABSOLUTE_URL_RE = re.compile(r"https?://[^\s<>\"')\]}]+")

# Relative paths like /products/electric-cars, preceded by a delimiter
_RELATIVE_URL_RE = re.compile(r"(?:^|[\s\"'(\[=:,;])(/[A-Za-z0-9_\-./%?#&=+~]+)")

# Markdown links: [text](url)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

_DANGEROUS_SCHEMES = ("javascript:", "data:", "vbscript:", "file:", "blob:")
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "tel:")

# Field names treated as URL carriers in custom (host-registered) components
_URL_FIELD_NAMES = {"url", "link", "href", "src", "image"}
_URL_FIELD_SUFFIXES = ("_url", "_link", "_href", "_src", "_image")

_TRAILING_PUNCTUATION = ".,;:!?'\""


def normalize_url(url: str) -> str:
    """Normalize a URL for comparison: trim spaces and trailing punctuation."""
    return url.strip().rstrip(_TRAILING_PUNCTUATION).rstrip("/") or "/"


# Internal alias
_clean_url = normalize_url


def extract_urls(text: Optional[str]) -> Set[str]:
    """Extract absolute and relative URLs from free text (prompts, RAG docs)."""
    if not text:
        return set()

    urls: Set[str] = set()
    for match in _ABSOLUTE_URL_RE.findall(text):
        urls.add(_clean_url(match))
    for match in _RELATIVE_URL_RE.findall(text):
        urls.add(_clean_url(match))
    return urls


class UrlGuard:
    """
    Validates generated URLs against the set of URLs present in the input.

    Args:
        allowed_urls: URLs collected from the request input.
        enforce_whitelist: When False, only dangerous schemes are blocked
            (escape hatch for hosts that cannot enumerate their URLs).
    """

    def __init__(
        self,
        allowed_urls: Optional[Iterable[str]] = None,
        enforce_whitelist: bool = True,
    ):
        self.enforce_whitelist = enforce_whitelist
        self._allowed: Set[str] = {
            _clean_url(u) for u in (allowed_urls or []) if u and str(u).strip()
        }
        self.removed_urls: List[str] = []

    def allow(self, *urls: Optional[str]) -> None:
        """Add input URLs to the whitelist."""
        for url in urls:
            if url and str(url).strip():
                self._allowed.add(_clean_url(str(url)))

    def allow_from_text(self, text: Optional[str]) -> None:
        """Extract and whitelist every URL found in input text."""
        self._allowed.update(extract_urls(text))

    def is_allowed(self, url: Optional[str]) -> bool:
        """Check a generated URL against scheme rules and the whitelist."""
        if not url or not str(url).strip():
            return False

        candidate = str(url).strip()
        lowered = candidate.lower()

        if any(lowered.startswith(scheme) for scheme in _DANGEROUS_SCHEMES):
            return False

        is_relative = candidate.startswith(("/", "#"))
        has_safe_scheme = any(lowered.startswith(s) for s in _SAFE_SCHEMES)
        if not is_relative and not has_safe_scheme:
            return False

        if not self.enforce_whitelist:
            return True

        return _clean_url(candidate) in self._allowed

    def check(self, url: Optional[str]) -> Optional[str]:
        """Return the URL if allowed, otherwise record and drop it."""
        if url is None:
            return None
        if self.is_allowed(url):
            return url
        self.removed_urls.append(str(url))
        return None

    # ------------------------------------------------------------------
    # Component sanitization
    # ------------------------------------------------------------------

    def sanitize_components(
        self,
        components: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Enforce URL rules on validated component dicts (wire format).

        Policy per component type:
        - bento: invented card link/image/action URLs are stripped; the
          card itself survives (content may still be valid).
        - buttons: a button whose URL is stripped is dropped (a dead
          action button is worse than no button); an empty buttons
          component is dropped entirely.
        - text: markdown links to non-allowed URLs collapse to their text.
        - chart: no URLs to check.
        - custom (host-registered) types: the data payload is walked
          recursively — URL-named fields (url, link, href, src, image,
          *_url, ...) are checked against the whitelist; any string value
          with a dangerous scheme or a non-allowed absolute URL is removed;
          markdown links inside text values are checked too.

        Returns:
            (sanitized_components, removed_urls)
        """
        self.removed_urls = []
        sanitized: List[Dict[str, Any]] = []

        for component in components:
            ctype = component.get("type")
            if ctype == "bento":
                sanitized.append(self._sanitize_bento(component))
            elif ctype == "buttons":
                cleaned = self._sanitize_buttons(component)
                if cleaned is not None:
                    sanitized.append(cleaned)
            elif ctype == "text":
                sanitized.append(self._sanitize_text(component))
            elif ctype == "chart":
                sanitized.append(component)
            else:
                sanitized.append(self._sanitize_custom(component))

        return sanitized, list(self.removed_urls)

    def _sanitize_bento(self, component: Dict[str, Any]) -> Dict[str, Any]:
        data = component.get("data", {})
        for card in data.get("cards", []):
            for field in ("link", "image"):
                if field in card and card[field] is not None:
                    checked = self.check(card[field])
                    if checked is None:
                        card.pop(field, None)
            action = card.get("action")
            if isinstance(action, dict) and action.get("url") is not None:
                if self.check(action["url"]) is None:
                    card.pop("action", None)
        return component

    def _sanitize_buttons(self, component: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = component.get("data", {})
        surviving = []
        for button in data.get("buttons", []):
            url = button.get("url")
            if url is None or self.check(url) is not None:
                surviving.append(button)
        if not surviving:
            return None
        data["buttons"] = surviving
        return component

    def _sanitize_text(self, component: Dict[str, Any]) -> Dict[str, Any]:
        data = component.get("data", {})
        content = data.get("content")
        if isinstance(content, str):
            data["content"] = self._strip_markdown_links(content)
        return component

    def _strip_markdown_links(self, content: str) -> str:
        """Collapse markdown links to their text when the URL is not allowed."""
        def _replace(match: re.Match) -> str:
            text, url = match.group(1), match.group(2)
            if self.is_allowed(url):
                return match.group(0)
            self.removed_urls.append(url)
            return text

        return _MARKDOWN_LINK_RE.sub(_replace, content)


    # Custom (host-registered) components: recursive walk

    def _sanitize_custom(self, component: Dict[str, Any]) -> Dict[str, Any]:
        data = component.get("data")
        if isinstance(data, (dict, list)):
            self._walk_custom(data)
        return component

    def _walk_custom(self, node: Any) -> None:
        if isinstance(node, dict):
            for key in list(node.keys()):
                value = node[key]
                if isinstance(value, str):
                    cleaned = self._sanitize_custom_string(key, value)
                    if cleaned is None:
                        node.pop(key)
                    else:
                        node[key] = cleaned
                elif isinstance(value, (dict, list)):
                    self._walk_custom(value)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    self._walk_custom(item)

    def _sanitize_custom_string(self, key: str, value: str) -> Optional[str]:
        """
        Sanitize a string field of a custom component.
        Returns the (possibly cleaned) value, or None to drop the field.
        """
        lowered_key = key.lower()
        if lowered_key in _URL_FIELD_NAMES or lowered_key.endswith(_URL_FIELD_SUFFIXES):
            return self.check(value)

        stripped = value.strip().lower()
        if any(stripped.startswith(s) for s in _DANGEROUS_SCHEMES):
            self.removed_urls.append(value)
            return None
        if stripped.startswith(("http://", "https://")):
            return self.check(value)
        if "](" in value:
            return self._strip_markdown_links(value)
        return value
