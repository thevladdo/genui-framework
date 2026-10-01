"""
Metrics Store
Aggregated impression/click counters per (tenant, zone, experiment, arm), used to compute the personalization uplift vs the control arm.

The experiment is part of the key: changing HOLDOUT_SALT reassigns every user, so counts from two assignments are not one sample.
Each counter has a verified twin, incremented only for events whose user passed the identity guard (arm computed by the server, not taken from the client).

The unit is the event, not the visitor: one visitor seeing a zone 10 times is 10 impressions.
The z-test assumes independent trials, which repeated exposures of the same visitor are not, so its p-value is reported as indicative.

Counters answer the headline question (CTR per arm, uplift %); the raw event stream goes to the audit log for offline slicing (per segment, per item, per time window).

Backends: Redis hashes when configured (shared, persistent), in-memory fallback otherwise.
Always fails open.
"""

from typing import Any, Dict, Optional

from utils.redis_conn import shared_redis

from .significance import two_proportion_significance

COUNTED_EVENTS = ("impression", "click")
VERIFIED_PREFIX = "verified:"


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

        self._conn = shared_redis(redis_url)

        # (tenant, zone_id, experiment, arm) -> {event_type: count}
        self._memory: Dict[tuple, Dict[str, int]] = {}

    async def _get_redis(self):
        """The shared Redis client, or None while unavailable (fail-open)."""
        return await self._conn.get()

    def _key(self, tenant: str, zone_id: str, experiment: str, arm: str) -> str:
        return f"{self.key_prefix}{tenant}:{zone_id}:{experiment}:{arm}"

    async def record(
        self,
        tenant: str,
        zone_id: str,
        experiment: str,
        arm: str,
        event_type: str,
        count: int = 1,
        verified: bool = False,
    ) -> None:
        """Increment a counter (and its verified twin). Unknown event types are counted too."""
        fields = [event_type] + ([VERIFIED_PREFIX + event_type] if verified else [])
        redis = await self._get_redis()
        if redis is not None:
            try:
                key = self._key(tenant, zone_id, experiment, arm)
                for field in fields:
                    await redis.hincrby(key, field, count)
                return
            except Exception as e:
                await self._conn.mark_failure(e)

        bucket = self._memory.setdefault((tenant, zone_id, experiment, arm), {})
        for field in fields:
            bucket[field] = bucket.get(field, 0) + count

    async def _arm_counts(
        self, tenant: str, zone_id: str, experiment: str, arm: str
    ) -> Dict[str, int]:
        redis = await self._get_redis()
        if redis is not None:
            try:
                raw = await redis.hgetall(self._key(tenant, zone_id, experiment, arm))
                return {k: int(v) for k, v in (raw or {}).items()}
            except Exception as e:
                await self._conn.mark_failure(e)

        return dict(self._memory.get((tenant, zone_id, experiment, arm), {}))

    async def stats(self, tenant: str, zone_id: str, experiment: str) -> Dict[str, Any]:
        """
        Per-arm counters of one experiment with CTR and the verified share, the personalization uplift ((ctr_personalized - ctr_control) / ctr_control), and the two-proportion z-test on events.
        """
        arms: Dict[str, Any] = {}
        for arm in ("personalized", "control", "none"):
            counts = await self._arm_counts(tenant, zone_id, experiment, arm)
            if not counts:
                continue
            verified = {
                k[len(VERIFIED_PREFIX):]: v for k, v in counts.items()
                if k.startswith(VERIFIED_PREFIX)
            }
            counts = {k: v for k, v in counts.items() if not k.startswith(VERIFIED_PREFIX)}
            arms[arm] = {
                **counts,
                "ctr": _ctr(counts.get("impression", 0), counts.get("click", 0)),
                "verified": verified,
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
            if significance is not None:
                significance["indicative"] = True

        return {
            "zone_id": zone_id,
            "experiment": experiment,
            "unit": "event",
            "arms": arms,
            "uplift_percent": uplift,
            "significance": significance,
        }
