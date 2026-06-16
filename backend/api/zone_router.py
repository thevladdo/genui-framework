"""
Zone Rendering API
Endpoint for rendering GenUI zones in landing pages.

Unlike the chat-based query endpoint, zones are:
- Automatically triggered on page mount (no user interaction needed)
- Pre-prompted by developers with context about the zone's location/purpose
- Configured with pinned content that must always appear
- Constrained to specific component types

Execution model (segment cache, stale-while-revalidate):
Renders are cached per (tenant, zone config, user segment) instead of
being generated per request. Most users collapse into a small number of
segments, so the LLM runs once per segment per TTL window:

- fresh hit: served from cache, no LLM call
- stale hit: served from cache immediately, re-rendered in background
  (single-flight: only one refresh per key runs at a time)
- miss: rendered live (cold start), then cached for the whole segment

Set cache_strategy="live" on a request (or zone_cache_enabled=false
globally) to bypass the cache for genuinely dynamic zones.

Security model:
- All endpoints require an API key (client keys for rendering, admin
  keys for warmup/stats). With no keys configured, auth is open (dev).
- When user_id is provided, the server-side profile is authoritative;
  the client-supplied profile only seeds the store on first sight.
- Every render is audit-logged: what was shown, to whom, from which
  segment and cache state.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.zone_agent import ZoneAgent, ZoneRenderRequest as ZoneAgentRequest, create_zone_agent
from api.deps import get_profile_store
from auth import AuthContext
from auth.dependencies import get_audit_logger, require_admin, require_client
from config import settings
from experiments import ARM_CONTROL, ARM_NONE, assign_arm
from segmentation import Segment, compute_segment
from utils.audit import summarize_shown_components
from utils.tracing import span
from utils.zone_cache import (
    ZoneRenderCache,
    build_cache_key,
    zone_config_hash,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zone", tags=["zones"])


# Request/Response Models
class PinnedContent(BaseModel):
    """Content that must always be displayed in the zone."""
    type: str = Field(..., description="Content type: link, article, document, custom")
    url: Optional[str] = Field(None, description="URL for links")
    title: str = Field(..., description="Display title")
    description: Optional[str] = Field(None, description="Optional description")
    id: Optional[str] = Field(None, description="ID for articles/documents")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class CustomComponentDef(BaseModel):
    """A host-registered component type available for this render."""
    name: str = Field(..., pattern="^[a-z][a-z0-9_-]{1,31}$")
    data_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema of the component's data payload"
    )
    description: Optional[str] = Field(
        "", description="One-liner telling the LLM when to use this component"
    )
    example: Optional[Dict[str, Any]] = Field(
        None, description="Optional example data payload shown to the LLM"
    )


class ZoneRenderRequest(BaseModel):
    """Request to render a GenUI zone."""
    zone_id: str = Field(..., description="Unique identifier for this zone")

    # Prompt engineering
    base_prompt: str = Field(
        default="Show relevant content for this user",
        description="Base prompt describing what the zone should display"
    )
    context_prompt: Optional[str] = Field(
        None,
        description="Developer-provided context about the zone's location and purpose"
    )

    # Content constraints
    pinned_content: Optional[List[PinnedContent]] = Field(
        default_factory=list,
        description="Content that must always be displayed"
    )

    # Rendering constraints
    preferred_component_type: Optional[str] = Field(
        None,
        description="Force a specific component type: bento, chart, text, buttons"
    )
    max_items: Optional[int] = Field(
        default=6,
        description="Maximum number of items to display"
    )

    # User context (from frontend)
    user_id: Optional[str] = Field(
        None,
        description="User ID: enables the server-side profile (authoritative) "
                    "and the audit trail"
    )
    user_profile: Optional[Dict[str, Any]] = Field(
        None,
        description="Client-side profile (IndexedDB cache). Used to seed the "
                    "server profile; ignored when a server profile exists"
    )
    behavior_data: Optional[Dict[str, Any]] = Field(
        None,
        description="User behavior data from BehaviorTracker"
    )

    # Page context
    current_page: Optional[str] = Field(
        None,
        description="Current page path (e.g., /homepage, /careers)"
    )
    page_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional page context (section, category, etc.). "
                    "Part of the cache key: keep it page-level, not per-user, "
                    "or every user gets their own cache entry."
    )

    # Caching
    cache_strategy: Optional[str] = Field(
        None,
        pattern="^(segment|live)$",
        description="'segment' (default): serve per-segment cached renders with "
                    "stale-while-revalidate. 'live': always call the LLM."
    )

    # Component vocabulary
    custom_components: Optional[List[CustomComponentDef]] = Field(
        None,
        description="Host-registered component types (name + JSON Schema + "
                    "description) available to the LLM for this zone. Part of "
                    "the cache key: changing them invalidates cached renders."
    )


class ZoneComponentData(BaseModel):
    """Component data for zone rendering."""
    type: str
    data: Dict[str, Any]
    layout: Optional[Dict[str, Any]] = None


class ZoneRenderResponse(BaseModel):
    """Response from zone rendering."""
    zone_id: str
    components: List[ZoneComponentData]
    pinned_content_included: List[str] = Field(
        default_factory=list,
        description="IDs/URLs of pinned content that was included"
    )
    personalization_applied: bool = Field(
        default=False,
        description="Whether personalization was applied based on user profile"
    )
    meta: Dict[str, Any] = Field(default_factory=dict)
    rendered_at: str


class ZoneWarmupRequest(BaseModel):
    """
    Request to pre-compute zone renders for known segments.

    Each entry is a normal ZoneRenderRequest whose user_profile/behavior_data
    describe a segment *archetype* (e.g. a developer interested in AI), not a
    real user. Run this offline (cron, deploy hook) so live traffic only ever
    sees cache hits.
    """
    zones: List[ZoneRenderRequest] = Field(
        ...,
        description="Zone requests with archetype profiles to pre-render"
    )


# Singletons
_zone_agent: Optional[ZoneAgent] = None
_zone_cache: Optional[ZoneRenderCache] = None


def get_zone_agent() -> ZoneAgent:
    """Get or create the zone agent singleton."""
    global _zone_agent
    if _zone_agent is None:
        _zone_agent = create_zone_agent()
    return _zone_agent


def get_zone_cache() -> ZoneRenderCache:
    """Get or create the zone render cache singleton."""
    global _zone_cache
    if _zone_cache is None:
        _zone_cache = ZoneRenderCache(
            redis_url=settings.redis_url,
            fresh_ttl=settings.zone_cache_fresh_ttl,
            stale_ttl=settings.zone_cache_stale_ttl,
            lock_ttl=settings.zone_cache_lock_ttl,
        )
    return _zone_cache


# Internal helpers
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_config(request: ZoneRenderRequest) -> Dict[str, Any]:
    """Developer-controlled zone configuration: the cacheable identity of a zone."""
    return {
        "zone_id": request.zone_id,
        "base_prompt": request.base_prompt,
        "context_prompt": request.context_prompt,
        "pinned_content": [p.model_dump() for p in (request.pinned_content or [])],
        "preferred_component_type": request.preferred_component_type,
        "max_items": request.max_items or 6,
        "current_page": request.current_page,
        "page_metadata": request.page_metadata or {},
        "custom_components": [
            c.model_dump() for c in (request.custom_components or [])
        ],
    }


def _segment_for(request: ZoneRenderRequest) -> Segment:
    return compute_segment(
        request.user_profile,
        request.behavior_data,
        min_confidence=settings.segment_min_confidence,
        max_interests=settings.segment_max_interests,
    )


def _cache_key_for(request: ZoneRenderRequest, segment: Segment, tenant: str) -> str:
    config_hash = zone_config_hash(_request_config(request))
    return build_cache_key(f"{tenant}:{request.zone_id}", config_hash, segment.key)


async def _resolve_profile(request: ZoneRenderRequest, auth: AuthContext) -> None:
    """
    Make the server-side profile authoritative.

    When user_id is present:
    - an existing server profile replaces the client-supplied one
    - otherwise the client profile (if any) seeds the server store,
      so the IndexedDB copy is demoted to a cache over time.
    """
    if not request.user_id:
        return

    store = get_profile_store()
    try:
        server_profile = await store.get(auth.tenant, request.user_id)
        if server_profile:
            request.user_profile = server_profile
        elif request.user_profile:
            request.user_profile = await store.sync_client_profile(
                auth.tenant, request.user_id, request.user_profile
            )
    except Exception as e:
        # Profile resolution must never break rendering
        logger.warning("Profile resolution failed for %s: %s", request.user_id, e)


def _agent_request(request: ZoneRenderRequest, tenant: str) -> ZoneAgentRequest:
    """Map the API request to the ZoneAgent request format."""
    return ZoneAgentRequest(
        zone_id=request.zone_id,
        base_prompt=request.base_prompt,
        context_prompt=request.context_prompt,
        pinned_content=[p.model_dump() for p in (request.pinned_content or [])],
        preferred_component_type=request.preferred_component_type,
        max_items=request.max_items or 6,
        user_profile=request.user_profile,
        behavior_data=request.behavior_data,
        current_page=request.current_page,
        page_metadata=request.page_metadata or {},
        custom_components=[
            c.model_dump() for c in (request.custom_components or [])
        ],
        tenant=tenant,
    )


def _payload_from_result(result) -> Dict[str, Any]:
    """Build the cacheable response payload from a ZoneRenderResult."""
    return {
        # Identity of this generated variant: users served the same cached payload share it, 
        # so events can be tied to the exact content shown
        "render_id": uuid.uuid4().hex[:12],
        "components": result.components,
        "pinned_content_included": result.pinned_content_included,
        "personalization_applied": result.personalization_applied,
        "meta": {
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "profile_factors": result.profile_factors_used,
            "sanitization": {
                "removed_urls": result.removed_urls,
                "dropped_components": result.dropped_components,
            },
        },
        "rendered_at": _utc_now(),
    }


async def _render_live(request: ZoneRenderRequest, tenant: str) -> Dict[str, Any]:
    """Run the ZoneAgent and return a cacheable response payload."""
    zone_agent = get_zone_agent()
    result = await zone_agent.render_zone_async(_agent_request(request, tenant))
    return _payload_from_result(result)


def _build_response(
    zone_id: str,
    payload: Dict[str, Any],
    cache_meta: Dict[str, Any],
    arm: str = ARM_NONE,
) -> ZoneRenderResponse:
    """Build the API response from a (possibly cached) render payload."""
    meta = dict(payload.get("meta", {}))
    meta["cache"] = cache_meta
    meta["render_id"] = payload.get("render_id")
    if arm != ARM_NONE or settings.holdout_percent > 0:
        meta["experiment"] = {
            "arm": arm,
            "holdout_percent": settings.holdout_percent,
        }

    return ZoneRenderResponse(
        zone_id=zone_id,
        components=[
            ZoneComponentData(
                type=c["type"],
                data=c["data"],
                layout=c.get("layout"),
            )
            for c in payload.get("components", [])
        ],
        pinned_content_included=payload.get("pinned_content_included", []),
        personalization_applied=payload.get("personalization_applied", False),
        meta=meta,
        rendered_at=payload.get("rendered_at", _utc_now()),
    )


def _audit_render(
    auth: AuthContext,
    request: ZoneRenderRequest,
    payload: Dict[str, Any],
    cache_meta: Dict[str, Any],
    arm: str = ARM_NONE,
) -> None:
    """Record what this render actually showed."""
    audit = get_audit_logger()
    audit.log(
        "zone_render",
        tenant=auth.tenant,
        user_id=request.user_id,
        key=auth.key_fingerprint,
        zone_id=request.zone_id,
        page=request.current_page,
        render_id=payload.get("render_id"),
        arm=arm,
        cache=cache_meta,
        personalization_applied=payload.get("personalization_applied", False),
        **summarize_shown_components(payload.get("components", [])),
    )


async def _refresh_in_background(request: ZoneRenderRequest, cache_key: str, tenant: str) -> None:
    """Re-render a stale entry and update the cache (single-flight)."""
    cache = get_zone_cache()
    try:
        payload = await _render_live(request, tenant)
        await cache.set(cache_key, payload)
        logger.info("Zone cache refreshed: %s", cache_key)
    except Exception as e:
        logger.error("Zone cache background refresh failed for %s: %s", cache_key, e)
    finally:
        await cache.release_refresh_lock(cache_key)


def _schedule_refresh(request: ZoneRenderRequest, cache_key: str, tenant: str) -> None:
    """Fire-and-forget refresh task; the lock guarantees one refresh per key."""
    asyncio.create_task(_refresh_in_background(request, cache_key, tenant))


async def _handle_render(request: ZoneRenderRequest, auth: AuthContext) -> ZoneRenderResponse:
    """Shared render flow used by /render and /batch-render."""
    with span(
        "genui.zone.render",
        zone_id=request.zone_id,
        tenant=auth.tenant,
    ) as render_span:
        await _resolve_profile(request, auth)

        # Control users get the NON-personalized render.
        # Stripping the signals makes them fall into the anonymous segment,
        # so the control arm shares the generic cached variant.
        arm = assign_arm(request.user_id, settings.holdout_percent, settings.holdout_salt)
        if arm == ARM_CONTROL:
            request.user_profile = None
            request.behavior_data = None

        strategy = request.cache_strategy or "segment"
        cache_bypassed = strategy == "live" or not settings.zone_cache_enabled

        def _annotate(cache_status: str, segment_key: Optional[str] = None) -> None:
            if render_span is not None:
                render_span.set_attribute("genui.cache.status", cache_status)
                render_span.set_attribute("genui.experiment.arm", arm)
                if segment_key:
                    render_span.set_attribute("genui.segment", segment_key)

        if cache_bypassed:
            payload = await _render_live(request, auth.tenant)
            cache_meta = {"status": "bypass", "strategy": strategy}
            _annotate("bypass")
            _audit_render(auth, request, payload, cache_meta, arm)
            return _build_response(request.zone_id, payload, cache_meta, arm)

        cache = get_zone_cache()
        segment = _segment_for(request)
        cache_key = _cache_key_for(request, segment, auth.tenant)

        lookup = await cache.get(cache_key)

        if lookup is not None:
            if lookup.status == "stale" and await cache.acquire_refresh_lock(cache_key):
                _schedule_refresh(request, cache_key, auth.tenant)

            cache_meta = {
                "status": lookup.status,
                "strategy": strategy,
                "segment": segment.key,
                "age_seconds": round(lookup.age_seconds, 1),
            }
            _annotate(lookup.status, segment.key)
            _audit_render(auth, request, lookup.payload, cache_meta, arm)
            return _build_response(request.zone_id, lookup.payload, cache_meta, arm)

        # Cold start: first request for this (tenant, zone config, segment)
        payload = await _render_live(request, auth.tenant)
        await cache.set(cache_key, payload)

        cache_meta = {"status": "miss", "strategy": strategy, "segment": segment.key}
        _annotate("miss", segment.key)
        _audit_render(auth, request, payload, cache_meta, arm)
        return _build_response(request.zone_id, payload, cache_meta, arm)


# API Endpoints
@router.post("/render", response_model=ZoneRenderResponse)
async def render_zone(
    request: ZoneRenderRequest,
    auth: AuthContext = Depends(require_client),
):
    """
    Render a GenUI zone with personalized content.

    This endpoint is called when a page with GenUIZone components loads.
    It combines:
    - Developer-provided prompts and constraints
    - The server-side user profile (authoritative when user_id is given)
    - Pinned content requirements

    Renders are served from the segment cache when possible; the LLM only
    runs on cold starts, background refreshes, or cache_strategy="live".
    """
    try:
        return await _handle_render(request, auth)
    except Exception as e:
        logger.error(f"Zone rendering failed for {request.zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _sse(event: str, data: Dict[str, Any]) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/render/stream")
async def render_zone_stream(
    request: ZoneRenderRequest,
    auth: AuthContext = Depends(require_client),
):
    """
    Render a GenUI zone as a Server-Sent Events stream (progressive render).

    Events:
    - `component`: one validated, sanitized component, emitted as soon as
      the model finishes generating it
    - `complete`: the authoritative final response (same shape as /render);
      clients should replace streamed state with it
    - `error`: terminal failure

    Cache hits stream their components immediately and complete in one
    round-trip; the LLM only streams live on cold starts or
    cache_strategy="live". Holdout, audit, and caching behave exactly
    like the non-streaming endpoint.
    """
    await _resolve_profile(request, auth)

    arm = assign_arm(request.user_id, settings.holdout_percent, settings.holdout_salt)
    if arm == ARM_CONTROL:
        request.user_profile = None
        request.behavior_data = None

    strategy = request.cache_strategy or "segment"
    cache_bypassed = strategy == "live" or not settings.zone_cache_enabled

    async def event_stream():
        try:
            cache = get_zone_cache()
            segment = None
            cache_key = None

            if not cache_bypassed:
                segment = _segment_for(request)
                cache_key = _cache_key_for(request, segment, auth.tenant)
                lookup = await cache.get(cache_key)

                if lookup is not None:
                    if lookup.status == "stale" and await cache.acquire_refresh_lock(cache_key):
                        _schedule_refresh(request, cache_key, auth.tenant)

                    for component in lookup.payload.get("components", []):
                        yield _sse("component", component)

                    cache_meta = {
                        "status": lookup.status,
                        "strategy": strategy,
                        "segment": segment.key,
                        "age_seconds": round(lookup.age_seconds, 1),
                    }
                    _audit_render(auth, request, lookup.payload, cache_meta, arm)
                    response = _build_response(request.zone_id, lookup.payload, cache_meta, arm)
                    yield _sse("complete", response.model_dump())
                    return

            # Live streaming render (cold start or bypass)
            zone_agent = get_zone_agent()
            agent_request = _agent_request(request, auth.tenant)

            async for event in zone_agent.render_zone_stream_async(agent_request):
                if event["type"] == "component":
                    yield _sse("component", event["component"])
                    continue

                # complete
                payload = _payload_from_result(event["result"])

                if cache_bypassed:
                    cache_meta = {"status": "bypass", "strategy": strategy}
                else:
                    await cache.set(cache_key, payload)
                    cache_meta = {
                        "status": "miss",
                        "strategy": strategy,
                        "segment": segment.key,
                    }

                _audit_render(auth, request, payload, cache_meta, arm)
                response = _build_response(request.zone_id, payload, cache_meta, arm)
                yield _sse("complete", response.model_dump())

        except Exception as e:
            logger.error(f"Zone stream failed for {request.zone_id}: {e}")
            yield _sse("error", {"detail": str(e), "zone_id": request.zone_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/batch-render")
async def batch_render_zones(
    requests: List[ZoneRenderRequest],
    auth: AuthContext = Depends(require_client),
):
    """
    Render multiple zones concurrently in a single request.

    Useful for pages with multiple GenUIZone components to reduce
    network round-trips.
    """

    async def _safe_render(request: ZoneRenderRequest) -> Dict[str, Any]:
        try:
            result = await _handle_render(request, auth)
            return {
                "zone_id": request.zone_id,
                "success": True,
                "data": result.model_dump(),
            }
        except Exception as e:
            return {
                "zone_id": request.zone_id,
                "success": False,
                "error": str(e),
            }

    results = await asyncio.gather(*[_safe_render(r) for r in requests])

    return {"results": list(results), "rendered_at": _utc_now()}


@router.post("/warmup")
async def warmup_zones(
    request: ZoneWarmupRequest,
    auth: AuthContext = Depends(require_admin),
):
    """
    Pre-compute zone renders for known segment archetypes (admin only).

    Call this offline (deploy hook, cron) with one entry per
    (zone, archetype profile) so that live traffic hits a warm cache.
    """
    if not settings.zone_cache_enabled:
        raise HTTPException(
            status_code=409,
            detail="Zone cache is disabled (zone_cache_enabled=false)",
        )

    cache = get_zone_cache()

    async def _warm_one(zone_request: ZoneRenderRequest) -> Dict[str, Any]:
        segment = _segment_for(zone_request)
        cache_key = _cache_key_for(zone_request, segment, auth.tenant)
        try:
            payload = await _render_live(zone_request, auth.tenant)
            await cache.set(cache_key, payload)
            return {
                "zone_id": zone_request.zone_id,
                "segment": segment.key,
                "success": True,
            }
        except Exception as e:
            logger.error("Zone warmup failed for %s: %s", zone_request.zone_id, e)
            return {
                "zone_id": zone_request.zone_id,
                "segment": segment.key,
                "success": False,
                "error": str(e),
            }

    results = await asyncio.gather(*[_warm_one(r) for r in request.zones])

    return {
        "results": list(results),
        "warmed": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "warmed_at": _utc_now(),
    }


@router.get("/cache/stats")
async def zone_cache_stats(auth: AuthContext = Depends(require_admin)):
    """Zone render cache statistics (admin only)."""
    cache = get_zone_cache()
    stats = await cache.stats()
    stats["enabled"] = settings.zone_cache_enabled
    return stats
