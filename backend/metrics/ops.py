"""
Operational metrics for the SRE, exposed at /metrics in Prometheus text
format: render latency, cache hit/miss, LLM generations, HTTP errors.

Counters live in a Redis hash via the shared reconnecting handle
(utils.redis_conn), the same pattern as MetricsStore: with multiple
workers every process increments the same counters, so any worker can
serve a truthful /metrics scrape. Without Redis (or during a blip)
counts fall back to process memory and are merged into the next scrape;
Prometheus rate() tolerates the resulting counter dips.

No prometheus_client dependency: the exposition text format is a few
lines, and the client library's per-process registries would need the
multiprocess machinery to be correct under uvicorn workers anyway.
"""

import asyncio
import logging
import re
from typing import Dict, Iterable, Mapping, Optional

from utils.redis_conn import shared_redis

logger = logging.getLogger(__name__)

_LABEL_ESCAPES = str.maketrans({"\\": r"\\", '"': r'\"', "\n": r"\n"})
_SUMMARY_SUFFIX = re.compile(r"_(sum|count)$")


def sample_key(name: str, labels: Optional[Mapping[str, str]] = None) -> str:
    """Prometheus sample identity: name{sorted="labels"} (stable across workers)."""
    if not labels:
        return name
    pairs = ",".join(
        f'{key}="{str(value).translate(_LABEL_ESCAPES)}"'
        for key, value in sorted(labels.items())
    )
    return f"{name}{{{pairs}}}"


def _format_value(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(value)


class OpsMetrics:
    """Cross-worker counters rendered in Prometheus text format."""

    def __init__(self, redis_url: Optional[str] = None, key: str = "genui:ops"):
        self._key = key
        self._conn = shared_redis(redis_url)
        self._memory: Dict[str, float] = {}  # fallback while Redis is unavailable
        self._tasks: set = set()  # strong refs: bare create_task may be GC'd mid-flight

    def observe(
        self,
        name: str,
        labels: Optional[Mapping[str, str]] = None,
        value: float = 1.0,
    ) -> None:
        """
        Fire-and-forget increment for hot paths: never blocks the request
        on a Redis round-trip and never raises (metrics must not break
        serving). Outside an event loop it counts in memory directly.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            field = sample_key(name, labels)
            self._memory[field] = self._memory.get(field, 0.0) + value
            return
        task = loop.create_task(self.inc(name, labels, value))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def observe_generation(
        self,
        tenant: str,
        op: str,
        seconds: Optional[float] = None,
        outcome: str = "ok",
    ) -> None:
        """One LLM generation (zone render or query): count + latency."""
        self.observe(
            "genui_llm_generations_total",
            {"tenant": tenant, "op": op, "outcome": outcome},
        )
        if seconds is not None:
            self.observe(
                "genui_llm_generation_seconds_sum", {"tenant": tenant, "op": op}, seconds
            )
            self.observe(
                "genui_llm_generation_seconds_count", {"tenant": tenant, "op": op}
            )

    def pending_tasks(self) -> Iterable[asyncio.Task]:
        """In-flight fire-and-forget writes (tests await these)."""
        return list(self._tasks)

    async def inc(
        self,
        name: str,
        labels: Optional[Mapping[str, str]] = None,
        value: float = 1.0,
    ) -> None:
        field = sample_key(name, labels)
        redis = await self._conn.get()
        if redis is not None:
            try:
                await redis.hincrbyfloat(self._key, field, value)
                return
            except Exception as e:
                await self._conn.mark_failure(e)
        self._memory[field] = self._memory.get(field, 0.0) + value

    async def render_text(
        self, extra_gauges: Optional[Mapping[str, float]] = None
    ) -> str:
        """
        The /metrics payload. Merges the shared Redis counters with any
        counts stranded in memory by a Redis flap, and appends scrape-time
        gauges (no I/O: statuses the process already knows).
        """
        samples: Dict[str, float] = {}
        redis = await self._conn.get()
        if redis is not None:
            try:
                raw = await redis.hgetall(self._key)
                samples = {field: float(value) for field, value in (raw or {}).items()}
            except Exception as e:
                await self._conn.mark_failure(e)
        for field, value in self._memory.items():
            samples[field] = samples.get(field, 0.0) + value

        samples[sample_key("genui_redis_connected")] = (
            1.0 if self._conn.status == "connected" else 0.0
        )
        for name, value in (extra_gauges or {}).items():
            samples[sample_key(name)] = float(value)

        lines = []
        typed = set()
        for field in sorted(samples):
            name = field.split("{", 1)[0]
            base = _SUMMARY_SUFFIX.sub("", name)
            if base != name:
                type_line = f"# TYPE {base} summary"
            elif name.endswith("_total"):
                type_line = f"# TYPE {name} counter"
            else:
                type_line = f"# TYPE {name} gauge"
            if type_line not in typed:
                typed.add(type_line)
                lines.append(type_line)
            lines.append(f"{field} {_format_value(samples[field])}")
        return "\n".join(lines) + "\n"


_ops: Optional[OpsMetrics] = None


def get_ops_metrics() -> OpsMetrics:
    """Process-wide OpsMetrics on the configured Redis (lazy, like the stores)."""
    global _ops
    if _ops is None:
        from config import settings

        _ops = OpsMetrics(redis_url=settings.redis_url)
    return _ops
