"""
Zone Rendering API
Endpoint for rendering GenUI zones in landing pages.

Unlike the chat-based query endpoint, zones are:
- Automatically triggered on page mount (no user interaction needed)
- Pre-prompted by developers with context about the zone's location/purpose
- Configured with pinned content that must always appear
- Constrained to specific component types
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.zone_agent import ZoneAgent, ZoneRenderRequest as ZoneAgentRequest, create_zone_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zone", tags=["zones"])


# ============================================
# Request/Response Models
# ============================================

class PinnedContent(BaseModel):
    """Content that must always be displayed in the zone."""
    type: str = Field(..., description="Content type: link, article, document, custom")
    url: Optional[str] = Field(None, description="URL for links")
    title: str = Field(..., description="Display title")
    description: Optional[str] = Field(None, description="Optional description")
    id: Optional[str] = Field(None, description="ID for articles/documents")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


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
    user_profile: Optional[Dict[str, Any]] = Field(
        None,
        description="User profile from IndexedDB"
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
        description="Additional page context (section, category, etc.)"
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


# ============================================
# Zone Agent Instance (singleton)
# ============================================

_zone_agent: Optional[ZoneAgent] = None

def get_zone_agent() -> ZoneAgent:
    """Get or create the zone agent singleton."""
    global _zone_agent
    if _zone_agent is None:
        _zone_agent = create_zone_agent()
    return _zone_agent


# ============================================
# API Endpoints
# ============================================

@router.post("/render", response_model=ZoneRenderResponse)
async def render_zone(request: ZoneRenderRequest):
    """
    Render a GenUI zone with personalized content.
    
    This endpoint is called when a page with GenUIZone components loads.
    It combines:
    - Developer-provided prompts and constraints
    - User profile and behavior data
    - Pinned content requirements
    
    To generate personalized UI components for the zone.
    """
    try:
        zone_agent = get_zone_agent()
        
        # Convert to agent request format
        agent_request = ZoneAgentRequest(
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
        )
        
        # Render the zone
        result = await zone_agent.render_zone_async(agent_request)
        
        # Format response
        return ZoneRenderResponse(
            zone_id=request.zone_id,
            components=[
                ZoneComponentData(
                    type=c["type"],
                    data=c["data"],
                    layout=c.get("layout"),
                )
                for c in result.components
            ],
            pinned_content_included=result.pinned_content_included,
            personalization_applied=result.personalization_applied,
            meta={
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "profile_factors": result.profile_factors_used,
            },
            rendered_at=datetime.utcnow().isoformat(),
        )
        
    except Exception as e:
        logger.error(f"Zone rendering failed for {request.zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-render")
async def batch_render_zones(requests: List[ZoneRenderRequest]):
    """
    Render multiple zones in a single request.
    
    Useful for pages with multiple GenUIZone components to reduce
    network round-trips.
    """
    results = []
    
    for request in requests:
        try:
            result = await render_zone(request)
            results.append({
                "zone_id": request.zone_id,
                "success": True,
                "data": result.model_dump(),
            })
        except HTTPException as e:
            results.append({
                "zone_id": request.zone_id,
                "success": False,
                "error": e.detail,
            })
        except Exception as e:
            results.append({
                "zone_id": request.zone_id,
                "success": False,
                "error": str(e),
            })
    
    return {"results": results, "rendered_at": datetime.utcnow().isoformat()}
