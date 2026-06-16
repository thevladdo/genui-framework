"""
Metrics Store
Aggregated impression/click counters per (tenant, zone, experiment arm),
used to compute the personalization uplift vs the control arm.

Counters answer the headline question (CTR per arm, uplift %); the raw
event stream goes to the audit log for offline slicing (per segment,
per item, per time window).

Backends: Redis hashes when configured (shared, persistent), in-memory
fallback otherwise. Always fails open.
"""

import logging
from typing import Any, Dict, Optional

from .significance import two_proportion_significance

logger = logging.getLogger(__name__)

COUNTED_EVENTS = ("impression", "click")


def _ctr(impressions: int, clicks: int) -> Optional[float]:
    if impressions <= 0:
        return None
    return round(clicks / impressions, 4)


class MetricsStore:
    """Async counter storage for zone events."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "genui:metrics:",
    ):
        self.key_prefix = key_prefix

        self._redis_url = redis_url
        self._redis = None
        self._redis_unavailable = False

        # (tenant, zone_id, arm) -> {event_type: count}
        self._memory: Dict[tuple, Dict[str, int]] = {}

    async def _get_redis(self):
        if not self._redis_url or self._redis_unavailable:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url, encoding="utf-8", decode_responses=True
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning("Metrics store: Redis unavailable (%s), using memory", e)
                self._redis = None
                self._redis_unavailable = True
        return self._redis

    def _key(self, tenant: str, zone_id: str, arm: str) -> str:
        return f"{self.key_prefix}{tenant}:{zone_id}:{arm}"

    async def record(
        self,
        tenant: str,
        zone_id: str,
        arm: str,
        event_type: str,
        count: int = 1,
    ) -> None:
        """Increment a counter. Unknown event types are counted too."""
        redis = await self._get_redis()
        if redis is not None:
            try:
                await redis.hincrby(self._key(tenant, zone_id, arm), event_type, count)
                return
            except Exception as e:
                logger.warning("Metrics store: Redis HINCRBY failed (%s)", e)

        bucket = self._memory.setdefault((tenant, zone_id, arm), {})
        bucket[event_type] = bucket.get(event_type, 0) + count

    async def _arm_counts(self, tenant: str, zone_id: str, arm: str) -> Dict[str, int]:
        redis = await self._get_redis()
        if redis is not None:
            try:
                raw = await redis.hgetall(self._key(tenant, zone_id, arm))
                return {k: int(v) for k, v in (raw or {}).items()}
            except Exception as e:
                logger.warning("Metrics store: Redis HGETALL failed (%s)", e)

        return dict(self._memory.get((tenant, zone_id, arm), {}))

    async def stats(self, tenant: str, zone_id: str) -> Dict[str, Any]:
        """
        Per-arm counters with CTR, the personalization uplift
        ((ctr_personalized - ctr_control) / ctr_control), and the
        statistical significance of the difference (two-proportion z-test).
        """
        arms: Dict[str, Any] = {}
        for arm in ("personalized", "control", "none"):
            counts = await self._arm_counts(tenant, zone_id, arm)
            if not counts:
                continue
            impressions = counts.get("impression", 0)
            clicks = counts.get("click", 0)
            arms[arm] = {
                **counts,
                "ctr": _ctr(impressions, clicks),
            }

        uplift = None
        personalized_ctr = (arms.get("personalized") or {}).get("ctr")
        control_ctr = (arms.get("control") or {}).get("ctr")
        if personalized_ctr is not None and control_ctr:
            uplift = round((personalized_ctr - control_ctr) / control_ctr * 100, 2)

        significance = None
        personalized = arms.get("personalized")
        control = arms.get("control")
        if personalized and control:
            significance = two_proportion_significance(
                impressions_a=personalized.get("impression", 0),
                clicks_a=personalized.get("click", 0),
                impressions_b=control.get("impression", 0),
                clicks_b=control.get("click", 0),
            )

        return {
            "zone_id": zone_id,
            "arms": arms,
            "uplift_percent": uplift,
            "significance": significance,
        }
