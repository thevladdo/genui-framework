"""
Per-request context (request id, tenant), log formatting, and the body of a 500.

The context is a dict held in a ContextVar: the middleware creates it, the auth dependency fills in the tenant, and logs, audit lines and spans read it without being passed anything.
It is a dict, not two ContextVars, because the endpoint runs in a copied context: a value set there would never reach the middleware that logs the failure.
"""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

REQUEST_ID_HEADER = "X-Request-ID"
GENERIC_ERROR = "Internal server error"

# An incoming id ends up in log lines and response headers: anything else is replaced by a fresh one.
_INCOMING_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("genui_request", default=None)

logger = logging.getLogger("genui.errors")


def begin_request(incoming_id: Optional[str]) -> str:
    request_id = incoming_id if incoming_id and _INCOMING_ID.match(incoming_id) else uuid.uuid4().hex
    _context.set({"request_id": request_id, "tenant": None})
    return request_id


def set_tenant(tenant: str) -> None:
    context = _context.get()
    if context is not None:
        context["tenant"] = tenant


def request_id() -> Optional[str]:
    context = _context.get()
    return context["request_id"] if context else None


def tenant() -> Optional[str]:
    context = _context.get()
    return context["tenant"] if context else None


def server_error(where: str) -> Dict[str, Any]:
    """
    Log the exception being handled, with its stack, and return what the client gets instead.

    The exception text names hosts, endpoints and functions: it goes to the log, never to the client.
    Call it from inside an except block.
    """
    logger.error("Unhandled error in %s", where, exc_info=True)
    return {"detail": GENERIC_ERROR, "request_id": request_id()}


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id() or "-"
        record.tenant = tenant() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Audit lines are already JSON and pass through unchanged."""

    def format(self, record: logging.LogRecord) -> str:
        if record.name == "genui.audit":
            return record.getMessage()
        line: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        if getattr(record, "tenant", "-") != "-":
            line["tenant"] = record.tenant
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str, ensure_ascii=False)


TEXT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s"


def configure_logging(log_format: str, level: int, stream=None) -> None:
    """In json mode the uvicorn loggers lose their own handlers and propagate to the root, so access and server lines reach the pipeline in the same format."""
    handler = logging.StreamHandler(stream)
    handler.addFilter(_ContextFilter())
    handler.setFormatter(JsonFormatter() if log_format == "json" else logging.Formatter(TEXT_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    if log_format == "json":
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uvicorn_logger = logging.getLogger(name)
            uvicorn_logger.handlers.clear()
            uvicorn_logger.propagate = True
