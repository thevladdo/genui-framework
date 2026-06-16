"""
OpenTelemetry tracing.

Two pieces:
- `span(name, **attributes)`: a context manager usable anywhere in the
  codebase. It is a no-op when OpenTelemetry is not installed or
  tracing is not configured, so instrumentation never becomes a hard
  dependency or a failure mode.
- `setup_tracing(app)`: called once at startup. With TRACING_ENABLED=true
  it configures the tracer provider (OTLP exporter when OTLP_ENDPOINT is
  set, console exporter otherwise) and instruments FastAPI.
"""

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace as _trace
except ImportError:
    _trace = None


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Optional[Any]]:
    """
    Start a span around a block of code. No-op without OpenTelemetry.

    None-valued attributes are skipped, so callers can pass optional
    context without filtering.
    """
    if _trace is None:
        yield None
        return

    tracer = _trace.get_tracer("genui")
    with tracer.start_as_current_span(name) as current_span:
        for key, value in attributes.items():
            if value is not None:
                try:
                    current_span.set_attribute(key, value)
                except Exception:
                    pass
        yield current_span


def setup_tracing(app=None) -> bool:
    """
    Configure tracing from settings. Returns True when tracing is active.

    Safe to call unconditionally: disabled settings or missing packages
    result in a no-op (logged), never an error.
    """
    from config import settings

    if not settings.tracing_enabled:
        return False

    if _trace is None:
        logger.warning("TRACING_ENABLED but opentelemetry is not installed")
        return False

    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({"service.name": "genui-backend"})
        provider = TracerProvider(resource=resource)

        if settings.otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
                )
                logger.info("Tracing: OTLP exporter -> %s", settings.otlp_endpoint)
            except ImportError:
                logger.warning(
                    "OTLP_ENDPOINT set but opentelemetry-exporter-otlp is not "
                    "installed; falling back to console exporter"
                )
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("Tracing: console exporter (set OTLP_ENDPOINT for a collector)")

        _trace.set_tracer_provider(provider)

        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(app)
            except ImportError:
                logger.warning("opentelemetry-instrumentation-fastapi not installed")

        return True

    except Exception as e:
        logger.error("Tracing setup failed: %s", e)
        return False
