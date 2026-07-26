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
import os
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
            self._file_logger.info(line)
            return

        logger.info(line)


class AuditReader:
    """
    Query side of the audit trail, always tenant-scoped.

    The base class is the honest answer for the production default
    (logger sink: the lines live in the host's log pipeline, which this
    backend cannot query): it reports queryable=False with a note,
    instead of an empty result that would read as "no events".
    """

    source = "log-pipeline"
    queryable = False
    note = (
        "Audit events are emitted on the 'genui.audit' logger and live in "
        "the host's log pipeline; query them there, or set AUDIT_LOG_PATH "
        "(single-worker file sink) to make them queryable from this API."
    )

    def query(
        self,
        tenant: str,
        *,
        user_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        event: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        return {"entries": [], "has_more": False}


class FileAuditReader(AuditReader):
    """
    Reads the JSONL file sink (AUDIT_LOG_PATH), rotated backups included,
    newest first.
    """

    source = "file"
    queryable = True
    note = ""

    def __init__(self, path: str):
        self.path = path

    def _files(self) -> List[str]:
        """Newest first: audit.jsonl, then .1, .2, ... (rotation order)."""
        files = [self.path]
        i = 1
        while os.path.exists(f"{self.path}.{i}"):
            files.append(f"{self.path}.{i}")
            i += 1
        return files

    @staticmethod
    def _matches(
        record: Dict[str, Any],
        tenant: str,
        user_id: Optional[str],
        zone_id: Optional[str],
        event: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> bool:
        if record.get("tenant") != tenant:
            return False
        if user_id is not None and record.get("user_id") != user_id:
            return False
        if zone_id is not None and record.get("zone_id") != zone_id:
            return False
        if event is not None and record.get("event") != event:
            return False
        if date_from or date_to:
            day = str(record.get("ts", ""))[:10]  # ISO date prefix
            if date_from and day < date_from:
                return False
            if date_to and day > date_to:
                return False
        return True

    def query(
        self,
        tenant: str,
        *,
        user_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        event: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        needed = offset + limit + 1  
        matches: List[Dict[str, Any]] = []
        for file_path in self._files():
            try:
                with open(file_path, encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue
            # newest last
            for line in reversed(lines):
                try:
                    record = json.loads(line)
                except ValueError:
                    continue 
                if not isinstance(record, dict):
                    continue
                if self._matches(
                    record, tenant, user_id, zone_id, event, date_from, date_to
                ):
                    matches.append(record)
                    if len(matches) >= needed:
                        break
            if len(matches) >= needed:
                break

        return {
            "entries": matches[offset:offset + limit],
            "has_more": len(matches) > offset + limit,
        }


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
