"""
Zone Agent Module
Specialized agent for rendering GenUI zones in landing pages.

Unlike the chat-based ResponseAgent, the ZoneAgent:
- Works with pre-defined prompts from developers
- Must include pinned content in responses
- Respects component type constraints
- Focuses on content curation rather than Q&A
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient

from config import settings
from rag import create_vector_store, build_context_from_results

logger = logging.getLogger(__name__)


@dataclass
class ZoneRenderRequest:
    """Request data for zone rendering."""
    zone_id: str
    base_prompt: str
    context_prompt: Optional[str]
    pinned_content: List[Dict[str, Any]]
    preferred_component_type: Optional[str]
    max_items: int
    user_profile: Optional[Dict[str, Any]]
    behavior_data: Optional[Dict[str, Any]]
    current_page: Optional[str]
    page_metadata: Dict[str, Any]


@dataclass
class ZoneRenderResult:
    """Result of zone rendering."""
    components: List[Dict[str, Any]]
    pinned_content_included: List[str]
    personalization_applied: bool
    confidence: float
    reasoning: str
    profile_factors_used: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "components": self.components,
            "pinned_content_included": self.pinned_content_included,
            "personalization_applied": self.personalization_applied,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "profile_factors_used": self.profile_factors_used,
        }


class ZoneAgent:
    """
    Agent specialized for rendering GenUI zones.
    
    Combines developer prompts, user profiles, and content retrieval
    to generate personalized zone content.
    """
    
    SYSTEM_PROMPT = """You are a content curator AI that generates personalized UI components for website zones.

Your task is to select and organize content that is most relevant to the user based on:
1. The zone's purpose (defined by the developer's prompts)
2. The user's profile, interests, and behavior
3. Pinned content that MUST be included
4. Any component type constraints

You MUST output valid JSON with this structure:
{
    "components": [
        {
            "type": "bento|chart|text|buttons",
            "data": { ... component-specific data ... },
            "layout": { ... optional layout hints ... }
        }
    ],
    "pinned_included": ["id1", "url1", ...],
    "personalization_applied": true|false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of content selection logic",
    "profile_factors": ["factor1", "factor2", ...]
}

COMPONENT TYPES:

1. "bento" - Grid of content cards (PREFERRED for content zones)
   data: {
       "cards": [
           {
               "title": "Card Title",
               "description": "Brief description",
               "icon": "emoji or icon name",
               "link": "https://...",
               "image": "image_url (optional)",
               "badge": "NEW (optional)",
               "metadata": { ... any extra data ... }
           }
       ],
       "columns": 2-4
   }

2. "text" - Introductory or explanatory text
   data: { "content": "markdown text", "style": "normal|emphasis|note|heading" }

3. "chart" - Data visualization (use sparingly in zones)
   data: { "chart_type": "bar|line|pie", "title": "...", "data": [...] }

4. "buttons" - Action buttons
   data: { "buttons": [{ "label": "...", "url": "...", "style": "primary|secondary|outline" }] }

CRITICAL RULES:

1. PINNED CONTENT IS MANDATORY: All items in pinned_content MUST appear in your output.
   Transform pinned content into appropriate card format within the component.

2. RESPECT COMPONENT TYPE CONSTRAINTS: If preferred_component_type is specified, 
   use ONLY that component type (usually "bento" for content zones).

3. PERSONALIZE BASED ON PROFILE: If user profile is available:
   - Developer/Engineer: Prioritize technical content, documentation, APIs
   - Business/Manager: Prioritize case studies, ROI content, executive summaries  
   - Student/Researcher: Prioritize educational content, tutorials, papers
   - Job seeker: Prioritize career pages, job openings, company culture
   - Consider interests, past behavior, and demographic information

4. MAX ITEMS: Do not exceed max_items total cards/items.

5. CONTENT RELEVANCE: Use retrieved documents to populate cards with real content
   from the knowledge base when available.
"""

    def __init__(self, model: str = None, vector_store=None):
        """Initialize the Zone Agent."""
        self.model = model or settings.response_model
        self.vector_store = vector_store or create_vector_store()
        
        self.client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=self.model,
        )
        
        self.agent = Agent(
            name="zone_agent",
            client=self.client,
            system_prompt=self.SYSTEM_PROMPT,
        )
        
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def render_zone(self, request: ZoneRenderRequest) -> ZoneRenderResult:
        """
        Render a GenUI zone synchronously.
        
        Args:
            request: Zone render request with all parameters
            
        Returns:
            ZoneRenderResult with components and metadata
        """
        prompt = self._build_zone_prompt(request)
        
        try:
            response = self.agent.run(prompt)
            response_text = self._extract_response_text(response)
            parsed = self._parse_response(response_text)
            
            return ZoneRenderResult(
                components=parsed.get("components", []),
                pinned_content_included=parsed.get("pinned_included", []),
                personalization_applied=parsed.get("personalization_applied", False),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", ""),
                profile_factors_used=parsed.get("profile_factors", []),
            )
            
        except Exception as e:
            logger.error(f"Zone rendering failed: {e}")
            return self._fallback_render(request)
    
    async def render_zone_async(self, request: ZoneRenderRequest) -> ZoneRenderResult:
        """Async wrapper for zone rendering."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.render_zone,
            request,
        )
    
    def _build_zone_prompt(self, request: ZoneRenderRequest) -> str:
        """Build the complete prompt for zone rendering."""
        parts = []
        
        # Zone identification and purpose
        parts.append(f"<zone_info>")
        parts.append(f"Zone ID: {request.zone_id}")
        parts.append(f"Page: {request.current_page or 'unknown'}")
        if request.page_metadata:
            parts.append(f"Page Context: {json.dumps(request.page_metadata)}")
        parts.append(f"</zone_info>")
        
        # Developer prompts (combined)
        parts.append(f"<zone_purpose>")
        parts.append(f"Base Purpose: {request.base_prompt}")
        if request.context_prompt:
            parts.append(f"Developer Context: {request.context_prompt}")
        parts.append(f"</zone_purpose>")
        
        # Constraints
        parts.append(f"<constraints>")
        parts.append(f"Max Items: {request.max_items}")
        if request.preferred_component_type:
            parts.append(f"REQUIRED Component Type: {request.preferred_component_type}")
        parts.append(f"</constraints>")
        
        # Pinned content (MUST include)
        if request.pinned_content:
            parts.append(f"<pinned_content>")
            parts.append("The following content MUST be included in your response:")
            for i, item in enumerate(request.pinned_content):
                parts.append(f"{i+1}. Type: {item.get('type')}, Title: {item.get('title')}, URL/ID: {item.get('url') or item.get('id')}")
                if item.get('description'):
                    parts.append(f"   Description: {item.get('description')}")
            parts.append(f"</pinned_content>")
        
        # User profile
        if request.user_profile:
            profile_summary = self._summarize_profile(request.user_profile)
            parts.append(f"<user_profile>\n{profile_summary}\n</user_profile>")
        
        # Behavior data summary
        if request.behavior_data:
            behavior_summary = self._summarize_behavior(request.behavior_data)
            parts.append(f"<user_behavior>\n{behavior_summary}\n</user_behavior>")
        
        # Retrieved content from knowledge base
        search_query = self._build_search_query(request)
        if search_query:
            results = self.vector_store.search(query=search_query, top_k=10)
            if results:
                context = build_context_from_results(results, max_tokens=1500)
                parts.append(f"<available_content>\n{context}\n</available_content>")
        
        parts.append("\nGenerate the zone content as valid JSON matching the specified structure.")
        parts.append("Remember: ALL pinned content MUST be included, and respect the component type constraint if specified.")
        
        return "\n\n".join(parts)
    
    def _build_search_query(self, request: ZoneRenderRequest) -> str:
        """Build a search query based on zone context and user profile."""
        query_parts = []
        
        query_parts.append(request.base_prompt)
        if request.context_prompt:
            query_parts.append(request.context_prompt)
        
        if request.user_profile:
            interests = request.user_profile.get("interests", {})
            if isinstance(interests, dict):
                for key, val in list(interests.items())[:3]:
                    if isinstance(val, dict) and "value" in val:
                        query_parts.append(str(val["value"]))
                    else:
                        query_parts.append(str(val))
            
            preferences = request.user_profile.get("preferences", {})
            if isinstance(preferences, dict):
                role = preferences.get("role", {})
                if isinstance(role, dict) and "value" in role:
                    query_parts.append(f"content for {role['value']}")
        
        return " ".join(query_parts[:5])
    
    def _summarize_profile(self, profile: Dict[str, Any]) -> str:
        """Create a concise profile summary for the prompt."""
        parts = []
        
        preferences = profile.get("preferences", {})
        if isinstance(preferences, dict) and preferences:
            pref_items = []
            for k, v in list(preferences.items())[:5]:
                if isinstance(v, dict) and "value" in v:
                    pref_items.append(f"{k}: {v['value']}")
                else:
                    pref_items.append(f"{k}: {v}")
            if pref_items:
                parts.append(f"Preferences: {', '.join(pref_items)}")
        
        interests = profile.get("interests", {})
        if isinstance(interests, dict) and interests:
            interest_items = []
            for k, v in list(interests.items())[:5]:
                if isinstance(v, dict) and "value" in v:
                    interest_items.append(str(v["value"]))
                else:
                    interest_items.append(str(v))
            if interest_items:
                parts.append(f"Interests: {', '.join(interest_items)}")
        
        demographic = profile.get("demographic", {})
        if isinstance(demographic, dict) and demographic:
            demo_items = []
            for k, v in list(demographic.items())[:3]:
                if isinstance(v, dict) and "value" in v:
                    demo_items.append(f"{k}: {v['value']}")
                else:
                    demo_items.append(f"{k}: {v}")
            if demo_items:
                parts.append(f"Demographics: {', '.join(demo_items)}")
        
        behavior = profile.get("behavior", {})
        if isinstance(behavior, dict):
            user_type = behavior.get("_user_type")
            if user_type:
                parts.append(f"User Type: {user_type}")
        
        return "\n".join(parts) if parts else "No profile data available."
    
    def _summarize_behavior(self, behavior: Dict[str, Any]) -> str:
        """Create a concise behavior summary."""
        parts = []
        
        if behavior.get("userType"):
            parts.append(f"Browsing Style: {behavior['userType']}")
        
        if behavior.get("maxScrollDepth"):
            depth = behavior["maxScrollDepth"]
            if depth > 80:
                parts.append("Reads content thoroughly")
            elif depth < 30:
                parts.append("Quick scanner, prefers concise content")
        
        if behavior.get("navigationPath"):
            recent_pages = behavior["navigationPath"][-3:]
            if recent_pages:
                parts.append(f"Recent pages: {', '.join(recent_pages)}")
        
        return "\n".join(parts) if parts else ""
    
    def _extract_response_text(self, response) -> str:
        """Extract text from agent response."""
        if hasattr(response, 'content'):
            content = response.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if hasattr(block, 'text'):
                        text_parts.append(block.text)
                    elif isinstance(block, dict) and 'text' in block:
                        text_parts.append(block['text'])
                    else:
                        text_parts.append(str(block))
                return "".join(text_parts)
            else:
                return str(content)
        return str(response)
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from agent."""
        try:
            if "TextBlock(content=" in response_text:
                start = response_text.find('{')
                end = response_text.rfind('}')
                if start != -1 and end != -1:
                    response_text = response_text[start:end+1]
            
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            return json.loads(response_text)
            
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse zone response: {e}")
            return {}
    
    def _fallback_render(self, request: ZoneRenderRequest) -> ZoneRenderResult:
        """Generate fallback content using only pinned content."""
        cards = []
        pinned_ids = []
        
        for item in request.pinned_content or []:
            card = {
                "title": item.get("title", "Untitled"),
                "description": item.get("description", ""),
                "link": item.get("url"),
            }
            cards.append(card)
            pinned_ids.append(item.get("url") or item.get("id") or item.get("title"))
        
        component_type = request.preferred_component_type or "bento"
        
        if component_type == "bento" and cards:
            components = [{
                "type": "bento",
                "data": {
                    "cards": cards,
                    "columns": min(len(cards), 3),
                },
            }]
        else:
            components = []
        
        return ZoneRenderResult(
            components=components,
            pinned_content_included=pinned_ids,
            personalization_applied=False,
            confidence=0.3,
            reasoning="Fallback render with only pinned content due to processing error",
            profile_factors_used=[],
        )
    
    def __del__(self):
        """Cleanup executor."""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)


def create_zone_agent(**kwargs) -> ZoneAgent:
    """Create a configured ZoneAgent instance."""
    return ZoneAgent(**kwargs)
