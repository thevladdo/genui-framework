"""
Audit Log
Append-only record of what was shown to whom — a compliance requirement
in regulated sectors, where "why did user X see content Y on date Z?"
must be answerable.

Events are JSON lines with a stable shape:
    {"ts": ..., "event": ..., "tenant": ..., "user_id": ..., ...payload}

Sink:
- AUDIT_LOG_PATH set   -> appended to a JSONL file (rotate externally)
- AUDIT_LOG_PATH empty -> emitted on the "genui.audit" logger (INFO),
  so any structured-logging pipeline can pick them up.

The raw API key is never audited — only its fingerprint.
"""

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("genui.audit")


class AuditLogger:
    """Append-only audit event writer (JSONL file or standard logger)."""

    def __init__(self, path: Optional[str] = None, enabled: bool = True):
        self.path = path or None
        self.enabled = enabled
        self._lock = threading.Lock()

    def log(
        self,
        event: str,
        tenant: str,
        user_id: Optional[str] = None,
        **payload: Any,
    ) -> None:
        """Record an audit event. Never raises: auditing must not break serving."""
        if not self.enabled:
            return

        record: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event,
            "tenant": tenant,
            "user_id": user_id,
        }
        record.update(payload)

        try:
            line = json.dumps(record, default=str, ensure_ascii=False)
        except Exception as e:
            logger.error("Audit serialization failed: %s", e)
            return

        if self.path:
            try:
                with self._lock:
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                return
            except OSError as e:
                logger.error("Audit file write failed (%s); falling back to logger", e)

        logger.info(line)


def summarize_shown_components(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compact summary of what a render actually displayed, for audit events:
    component types, card/button titles, and every link shown.
    """
    types: List[str] = []
    titles: List[str] = []
    links: List[str] = []

    for component in components or []:
        ctype = component.get("type", "unknown")
        types.append(ctype)
        data = component.get("data", {}) or {}

        if ctype == "bento":
            for card in data.get("cards", []) or []:
                if card.get("title"):
                    titles.append(str(card["title"]))
                if card.get("link"):
                    links.append(str(card["link"]))
        elif ctype == "buttons":
            for button in data.get("buttons", []) or []:
                if button.get("label"):
                    titles.append(str(button["label"]))
                if button.get("url"):
                    links.append(str(button["url"]))

    return {
        "component_types": types,
        "shown_titles": titles,
        "shown_links": links,
    }
