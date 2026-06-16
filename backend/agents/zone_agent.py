"""
Zone Agent Module
Specialized agent for rendering GenUI zones in landing pages.

Unlike the chat-based ResponseAgent, the ZoneAgent:
- Works with pre-defined prompts from developers
- Must include pinned content in responses
- Respects component type constraints
- Focuses on content curation rather than Q&A

Output guarantees (enforced by the system, not by the prompt):
- The model is constrained with provider-native structured output
  (response_format json_schema, falling back to json_object).
- Every component is validated against the Pydantic schemas in
  backend/schemas; invalid components are dropped, not propagated.
- URLs in the output must exist in the input (pinned content, developer
  prompts, RAG documents, page context) — invented URLs are stripped
  by the UrlGuard.
- Pinned content is verified after generation and appended if missing.
"""

import asyncio
import copy
import logging
import json
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from config import settings
from llm import create_llm_client
from rag import create_vector_store, build_context_from_results
from schemas import (
    component_to_dict,
    merge_custom_types,
    validate_components,
    zone_output_json_schema,
)
from utils.json_stream import ComponentStreamParser
from utils.url_guard import UrlGuard, normalize_url

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
    custom_components: Optional[List[Dict[str, Any]]] = None
    # Tenant scope for knowledge-base retrieval
    tenant: Optional[str] = None


@dataclass
class ZoneRenderResult:
    """Result of zone rendering."""
    components: List[Dict[str, Any]]
    pinned_content_included: List[str]
    personalization_applied: bool
    confidence: float
    reasoning: str
    profile_factors_used: List[str] = field(default_factory=list)
    removed_urls: List[str] = field(default_factory=list)
    dropped_components: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "components": self.components,
            "pinned_content_included": self.pinned_content_included,
            "personalization_applied": self.personalization_applied,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "profile_factors_used": self.profile_factors_used,
            "removed_urls": self.removed_urls,
            "dropped_components": self.dropped_components,
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
   data: { "chart_type": "bar|line|pie|area|donut", "title": "...", "data": [{"label": "...", "value": 0}] }

4. "buttons" - Action buttons
   data: { "buttons": [{ "label": "...", "url": "...", "style": "primary|secondary|outline|ghost|shine|gooey|expandIcon|ringHover" }] }

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

5. NEVER INVENT URLS: Every link or image URL in your output MUST be copied
   verbatim from the input (pinned content, developer context, or available
   content). URLs not present in the input will be removed by the system.

6. CONTENT RELEVANCE: Use retrieved documents to populate cards with real content
   from the knowledge base when available.
"""

    def __init__(self, model: str = None, vector_store=None, llm_client=None):
        """Initialize the Zone Agent."""
        self.model = model or settings.response_model
        self.vector_store = vector_store or create_vector_store()
        self.llm = llm_client or create_llm_client(self.model)
    
    
    # Public API
    async def render_zone_async(self, request: ZoneRenderRequest) -> ZoneRenderResult:
        """
        Render a GenUI zone.

        Args:
            request: Zone render request with all parameters

        Returns:
            ZoneRenderResult with validated, sanitized components
        """
        try:
            custom_types = merge_custom_types(request.custom_components)
            retrieved = await self._retrieve_results(request)
            prompt = self._build_zone_prompt(request, retrieved, custom_types)

            response_text = await self._call_llm(prompt, custom_types)
            parsed = self._parse_response(response_text)

            return self._validate_and_sanitize(request, retrieved, parsed, custom_types)

        except Exception as e:
            logger.error(f"Zone rendering failed: {e}")
            return self._fallback_render(request)

    def render_zone(self, request: ZoneRenderRequest) -> ZoneRenderResult:
        """Synchronous wrapper for backwards compatibility."""
        return asyncio.run(self.render_zone_async(request))

    async def render_zone_stream_async(
        self,
        request: ZoneRenderRequest,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Render a zone progressively. Yields events:

            {"type": "component", "component": {...}}
                — one per generated component, already validated against
                  the schemas and passed through the URL whitelist
            {"type": "complete", "result": ZoneRenderResult}
                — the authoritative final result (includes pinned-content
                  enforcement; clients should replace streamed state with it)

        Any failure degrades to a single complete event with the
        fallback render — the stream never errors out mid-way.
        """
        try:
            custom_types = merge_custom_types(request.custom_components)
            retrieved = await self._retrieve_results(request)
            prompt = self._build_zone_prompt(request, retrieved, custom_types)
            guard = self._build_url_guard(request, retrieved)

            parser = ComponentStreamParser()
            emitted: List[Dict[str, Any]] = []
            dropped: List[str] = []
            removed_urls: List[str] = []

            async for delta in self.llm.stream_json(self.SYSTEM_PROMPT, prompt):
                for raw_component in parser.feed(delta):
                    valid, errors = validate_components([raw_component], custom_types)
                    dropped.extend(errors)
                    if not valid:
                        continue
                    component = component_to_dict(valid[0])
                    sanitized, removed = guard.sanitize_components([component])
                    removed_urls.extend(removed)
                    if not sanitized:
                        continue
                    emitted.append(sanitized[0])
                    yield {"type": "component", "component": sanitized[0]}

            parsed = self._parse_response(parser.text)

            # Pinned enforcement on a copy: the streamed dicts must not be
            # mutated after they have been yielded
            components, pinned_included = self._enforce_pinned(
                copy.deepcopy(emitted),
                request.pinned_content or [],
                request.max_items,
            )

            yield {
                "type": "complete",
                "result": ZoneRenderResult(
                    components=components,
                    pinned_content_included=pinned_included,
                    personalization_applied=bool(parsed.get("personalization_applied", False)),
                    confidence=float(parsed.get("confidence", 0.5)),
                    reasoning=str(parsed.get("reasoning", "")),
                    profile_factors_used=list(parsed.get("profile_factors", [])),
                    removed_urls=removed_urls,
                    dropped_components=dropped,
                ),
            }

        except Exception as e:
            logger.error(f"Zone stream rendering failed: {e}")
            yield {"type": "complete", "result": self._fallback_render(request)}


    # LLM call with provider-native structured output
    async def _call_llm(self, prompt: str, custom_types=None) -> str:
        """
        Call the LLM constrained to JSON output through the provider
        abstraction. Provider-native structured output is used where
        supported; server-side validation applies either way.
        """
        return await self.llm.complete_json(
            system=self.SYSTEM_PROMPT,
            user=prompt,
            json_schema=zone_output_json_schema(custom_types),
        )


    # Validation, URL whitelist, pinned enforcement  
    def _validate_and_sanitize(
        self,
        request: ZoneRenderRequest,
        retrieved: List[Any],
        parsed: Dict[str, Any],
        custom_types: Optional[Dict[str, Any]] = None,
    ) -> ZoneRenderResult:
        """Turn raw LLM output into a guaranteed-valid render result."""
        # 1. Schema validation, component by component (built-in Pydantic schemas + host-registered JSON Schemas)
        valid_models, dropped = validate_components(
            parsed.get("components", []), custom_types
        )
        components = [component_to_dict(c) for c in valid_models]

        # 2. URL whitelist: only URLs that existed in the input survive
        guard = self._build_url_guard(request, retrieved)
        components, removed_urls = guard.sanitize_components(components)

        # 3. Pinned content: verified on the actual output, not on the model's claims; missing items are appended
        components, pinned_included = self._enforce_pinned(
            components, request.pinned_content or [], request.max_items
        )

        return ZoneRenderResult(
            components=components,
            pinned_content_included=pinned_included,
            personalization_applied=bool(parsed.get("personalization_applied", False)),
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=str(parsed.get("reasoning", "")),
            profile_factors_used=list(parsed.get("profile_factors", [])),
            removed_urls=removed_urls,
            dropped_components=dropped,
        )

    def _build_url_guard(
        self,
        request: ZoneRenderRequest,
        retrieved: List[Any],
    ) -> UrlGuard:
        """Whitelist every URL that legitimately exists in the input."""
        guard = UrlGuard(enforce_whitelist=settings.url_whitelist_enabled)

        # Developer prompts (context prompts typically enumerate content)
        guard.allow_from_text(request.base_prompt)
        guard.allow_from_text(request.context_prompt)

        # Pinned content
        for item in request.pinned_content or []:
            guard.allow(item.get("url"), item.get("id"))
            for value in (item.get("metadata") or {}).values():
                if isinstance(value, str):
                    guard.allow_from_text(value)

        # Page context
        guard.allow(request.current_page)
        for value in (request.page_metadata or {}).values():
            if isinstance(value, str):
                guard.allow_from_text(value)

        # Retrieved documents (content + metadata)
        for result in retrieved:
            metadata = getattr(result, "metadata", None) or {}
            guard.allow(metadata.get("url"), metadata.get("image"))
            guard.allow_from_text(getattr(result, "content", None))

        return guard

    def _enforce_pinned(
        self,
        components: List[Dict[str, Any]],
        pinned_content: List[Dict[str, Any]],
        max_items: int,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Guarantee every pinned item appears in the output.

        Presence is computed from the actual components (by URL or title);
        missing items are appended as cards to the first bento component
        (or a new one when none exists).
        """
        if not pinned_content:
            return components, []

        links: Set[str] = set()
        titles: Set[str] = set()
        for component in components:
            data = component.get("data", {})
            if component.get("type") == "bento":
                for card in data.get("cards", []):
                    if card.get("link"):
                        links.add(normalize_url(str(card["link"])))
                    if card.get("title"):
                        titles.add(str(card["title"]).strip().lower())
            elif component.get("type") == "buttons":
                for button in data.get("buttons", []):
                    if button.get("url"):
                        links.add(normalize_url(str(button["url"])))

        included: List[str] = []
        missing: List[Dict[str, Any]] = []
        for item in pinned_content:
            identifier = item.get("url") or item.get("id") or item.get("title", "")
            url = item.get("url")
            title = (item.get("title") or "").strip().lower()
            if (url and normalize_url(str(url)) in links) or (title and title in titles):
                included.append(identifier)
            else:
                missing.append(item)

        if missing:
            extra_cards = []
            for item in missing:
                card = {
                    "title": item.get("title", "Untitled"),
                    "description": item.get("description") or "",
                }
                if item.get("url"):
                    card["link"] = item["url"]
                extra_cards.append(card)
                included.append(item.get("url") or item.get("id") or item.get("title", ""))

            target = next(
                (c for c in components if c.get("type") == "bento"), None
            )
            if target is not None:
                cards = target["data"].get("cards", [])
                # Pinned content wins over generated content within max_items
                overflow = len(cards) + len(extra_cards) - max(max_items, len(extra_cards))
                if overflow > 0:
                    cards = cards[:-overflow]
                target["data"]["cards"] = cards + extra_cards
            else:
                components.append({
                    "type": "bento",
                    "data": {
                        "cards": extra_cards,
                        "columns": min(max(len(extra_cards), 1), 3),
                    },
                })

        return components, included


    # Retrieval and prompt building
    async def _retrieve_results(self, request: ZoneRenderRequest) -> List[Any]:
        """Retrieve knowledge-base content relevant to the zone."""
        search_query = self._build_search_query(request)
        if not search_query:
            return []
        try:
            return await self.vector_store.search_async(
                query=search_query,
                top_k=10,
                tenant=request.tenant,
            )
        except Exception as e:
            logger.warning(f"Zone retrieval failed, continuing without RAG: {e}")
            return []

    def _build_zone_prompt(
        self,
        request: ZoneRenderRequest,
        retrieved: List[Any],
        custom_types: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the complete prompt for zone rendering."""
        parts = []

        # Host-registered component types extend the LLM's vocabulary
        if custom_types:
            parts.append("<custom_components>")
            parts.append(
                "In addition to the built-in component types, the following "
                "host-registered types are available. Their data MUST match "
                "the given JSON schema exactly:"
            )
            for definition in custom_types.values():
                parts.append(definition.prompt_doc())
            parts.append("</custom_components>")

        # Zone identification and purpose
        parts.append("<zone_info>")
        parts.append(f"Zone ID: {request.zone_id}")
        parts.append(f"Page: {request.current_page or 'unknown'}")
        if request.page_metadata:
            parts.append(f"Page Context: {json.dumps(request.page_metadata)}")
        parts.append("</zone_info>")

        # Developer prompts (combined)
        parts.append("<zone_purpose>")
        parts.append(f"Base Purpose: {request.base_prompt}")
        if request.context_prompt:
            parts.append(f"Developer Context: {request.context_prompt}")
        parts.append("</zone_purpose>")

        # Constraints
        parts.append("<constraints>")
        parts.append(f"Max Items: {request.max_items}")
        if request.preferred_component_type:
            parts.append(f"REQUIRED Component Type: {request.preferred_component_type}")
        parts.append("</constraints>")

        # Pinned content (MUST include)
        if request.pinned_content:
            parts.append("<pinned_content>")
            parts.append("The following content MUST be included in your response:")
            for i, item in enumerate(request.pinned_content):
                parts.append(f"{i+1}. Type: {item.get('type')}, Title: {item.get('title')}, URL/ID: {item.get('url') or item.get('id')}")
                if item.get('description'):
                    parts.append(f"   Description: {item.get('description')}")
            parts.append("</pinned_content>")

        # User profile
        if request.user_profile:
            profile_summary = self._summarize_profile(request.user_profile)
            parts.append(f"<user_profile>\n{profile_summary}\n</user_profile>")

        # Behavior data summary
        if request.behavior_data:
            behavior_summary = self._summarize_behavior(request.behavior_data)
            parts.append(f"<user_behavior>\n{behavior_summary}\n</user_behavior>")

        # Retrieved content from knowledge base
        if retrieved:
            context = build_context_from_results(retrieved, max_tokens=1500)
            parts.append(f"<available_content>\n{context}\n</available_content>")

        parts.append("\nGenerate the zone content as valid JSON matching the specified structure.")
        parts.append("Remember: ALL pinned content MUST be included, respect the component type constraint, and use ONLY URLs present in the input above.")

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

    # ------------------------------------------------------------------
    # Parsing and fallback
    # ------------------------------------------------------------------

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse JSON response. With response_format enforced the content is
        already pure JSON; code-fence stripping is kept as a defensive net.
        """
        try:
            text = response_text.strip()
            if text.startswith("```"):
                first_newline = text.find("\n")
                text = text[first_newline + 1:]
                if text.rstrip().endswith("```"):
                    text = text.rstrip()[:-3]
            return json.loads(text)
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


def create_zone_agent(**kwargs) -> ZoneAgent:
    """Create a configured ZoneAgent instance."""
    return ZoneAgent(**kwargs)
