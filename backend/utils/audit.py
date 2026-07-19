"""
Audit Log
Append-only record of what was shown to whom, a compliance requirement
in regulated sectors, where "why did user X see content Y on date Z?"
must be answerable.

Events are JSON lines with a stable shape:
    {"ts": ..., "event": ..., "tenant": ..., "user_id": ..., ...payload}

Sink:
- AUDIT_LOG_PATH empty (production default) -> emitted on the
  "genui.audit" logger (INFO), so the host's structured-logging
  pipeline ships, retains and indexes the lines (multi-worker safe:
  every replica feeds the same pipeline).
- AUDIT_LOG_PATH set -> appended to a JSONL file with stdlib size
  rotation (AUDIT_LOG_MAX_BYTES / AUDIT_LOG_BACKUP_COUNT). Rotation is
  per-process: use the file sink only with a single worker, or point
  each worker at its own file.

The raw API key is never audited, only its fingerprint.
"""

import json
import logging
import logging.handlers
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("genui.audit")


class AuditLogger:
    """Append-only audit event writer (rotating JSONL file or standard logger)."""

    def __init__(
        self,
        path: Optional[str] = None,
        enabled: bool = True,
        max_bytes: int = 0,
        backup_count: int = 0,
    ):
        self.path = path or None
        self.enabled = enabled
        self._file_logger: Optional[logging.Logger] = None
        if self.path and self.enabled:
            try:
                # Eager open: an unwritable path must fail HERE (visible, # with logger fallback).
                handler = logging.handlers.RotatingFileHandler(
                    self.path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                handler.setFormatter(logging.Formatter("%(message)s"))
                # Constructed directly (not via getLogger): 
                # each AuditLoggerowns its handler, so instances never stack handlers 
                # on a shared registry entry and double-write lines.
                file_logger = logging.Logger("genui.audit.file", level=logging.INFO)
                file_logger.addHandler(handler)
                self._file_logger = file_logger
            except OSError as e:
                logger.error(
                    "Audit file sink unavailable (%s); falling back to the "
                    "'genui.audit' logger", e
                )

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

        if self._file_logger is not None:
            # Rotation and locking via stdlib; write errors are reported by logging.Handler.handleError (stderr).
            self._file_logger.info(line)
            return

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
