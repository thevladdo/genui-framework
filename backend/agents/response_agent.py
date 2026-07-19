"""
Response Agent Module
Handles user queries using RAG retrieval and user profile context.
Generates structured responses suitable for GenUI rendering.

Isolation invariant: the agent instance holds NO conversational state.
Everything the model sees (profile, history, retrieved context, tenant)
lives in the single request; two sequential queries can never share
context, across users or tenants.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json

from config import settings
from llm import create_llm_client
from rag import create_vector_store, build_context_from_results
from schemas import component_to_dict, validate_components
from utils.content_policy import policy_for
from utils.numeric_guard import NumericGuard
from utils.url_guard import UrlGuard

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """User profile data from IndexedDB."""
    user_id: str
    preferences: Dict[str, Any]
    interests: Dict[str, Any]
    demographic: Dict[str, Any]
    behavior: Dict[str, Any]
    history_summary: str
    interaction_patterns: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=data.get("userId", data.get("user_id", "anonymous")),
            preferences=data.get("preferences", {}),
            interests=data.get("interests", {}),
            demographic=data.get("demographic", {}),
            behavior=data.get("behavior", {}),
            history_summary=data.get("history_summary", ""),
            interaction_patterns=data.get("interaction_patterns", {}),
        )
    
    def to_context(self) -> str:
        """Convert profile to context string for LLM."""
        parts = []
        
        # Demographic information (name, role, etc.)
        if self.demographic:
            demo_items = []
            for key, value in self.demographic.items():
                # Handle nested value/confidence structure
                if isinstance(value, dict) and 'value' in value:
                    actual_value = value['value']
                    confidence = value.get('confidence', 1.0)
                    if confidence > 0.7:  # Only include high-confidence demographic data
                        demo_items.append(f"{key}: {actual_value}")
                else:
                    demo_items.append(f"{key}: {value}")
            
            if demo_items:
                parts.append("User Demographics:\n- " + "\n- ".join(demo_items))
        
        # Interests
        if self.interests:
            interest_items = []
            for key, value in self.interests.items():
                if isinstance(value, dict) and 'value' in value:
                    actual_value = value['value']
                    interest_items.append(f"{key}: {actual_value}")
                else:
                    interest_items.append(f"{key}: {value}")
            
            if interest_items:
                parts.append("User Interests:\n- " + "\n- ".join(interest_items))
        
        # Preferences
        if self.preferences:
            pref_items = []
            for key, value in self.preferences.items():
                if isinstance(value, dict) and 'value' in value:
                    actual_value = value['value']
                    pref_items.append(f"{key}: {actual_value}")
                else:
                    pref_items.append(f"{key}: {value}")
            
            if pref_items:
                parts.append("User Preferences:\n- " + "\n- ".join(pref_items))
        
        # Behavior patterns
        if self.behavior:
            behavior_items = []
            for key, value in self.behavior.items():
                if isinstance(value, dict) and 'value' in value:
                    actual_value = value['value']
                    behavior_items.append(f"{key}: {actual_value}")
                else:
                    behavior_items.append(f"{key}: {value}")
            
            if behavior_items:
                parts.append("Observed Behavior:\n- " + "\n- ".join(behavior_items))
        
        if self.history_summary:
            parts.append(f"Interaction History: {self.history_summary}")
        
        return "\n\n".join(parts) if parts else "No user profile available."


@dataclass 
class GenUIComponent:
    """Structured component for frontend rendering."""
    type: str  # "bento", "chart", "text", "buttons", etc.
    data: Dict[str, Any]
    layout: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type, "data": self.data}
        if self.layout:
            result["layout"] = self.layout
        return result


@dataclass
class AgentResponse:
    """Structured response from the Response Agent."""
    text_response: str
    components: List[GenUIComponent]
    sources: List[Dict[str, str]]
    confidence: float
    suggested_actions: List[str]
    sanitization: Dict[str, Any] = None

    def __post_init__(self):
        if self.sanitization is None:
            self.sanitization = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_response": self.text_response,
            "components": [c.to_dict() for c in self.components],
            "sources": self.sources,
            "confidence": self.confidence,
            "suggested_actions": self.suggested_actions,
            "sanitization": self.sanitization,
        }


class ResponseAgent:
    """
    Agent responsible for answering user queries.
    
    Uses RAG for knowledge retrieval and considers user profile
    for personalized responses. Outputs structured data for GenUI rendering.
    """
    
    SYSTEM_PROMPT = """You are a helpful assistant that provides informative, personalized responses.
Your responses should be structured to enable dynamic UI generation.

CRITICAL: ALWAYS adapt your response style and content based on the user's profile:
- If the user is a developer/engineer, use technical language, code examples, and architectural details
- If the user is a business person, focus on ROI, business value, and practical outcomes
- If the user has specific interests, relate answers to those topics when relevant
- If the user has stated preferences (e.g., brief vs detailed), honor them
- If you know the user's name or role, acknowledge it naturally in your response

The user's profile (if available) will be provided in <user_profile> tags. USE THIS INFORMATION to personalize your response appropriately.

When responding, you MUST output valid JSON with this structure:
{
    "text_response": "Your main response text",
    "components": [
        {
            "type": "text|bento|chart|buttons|tabs_feature|steps_section|stats_banner|testimonial_carousel|pricing_cards|content_grid|hero_banner",
            "data": { ... component-specific data ... },
            "layout": { ... optional layout hints ... }
        }
    ],
    "sources": [{"title": "...", "url": "..."}],
    "confidence": 0.0-1.0,
    "suggested_actions": ["action1", "action2"]
}

Component types and their data structures:

1. "text" - Simple text response
   data: { "content": "markdown text", "style": "normal|emphasis|note" }

2. "bento" - Card grid layout
   data: { 
       "cards": [
           { "title": "...", "description": "...", "icon": "...", "link": "..." }
       ],
       "columns": 2-4
   }

3. "chart" - Data visualization
   data: {
       "chart_type": "bar|line|pie|area|donut",
       "title": "Chart Title",
       "data": [{ "label": "...", "value": ... }],
       "x_axis": "...",
       "y_axis": "..."
   }

4. "buttons" - Action buttons with links
   data: {
       "buttons": [
           { "label": "...", "url": "...", "style": "primary|secondary|outline|ghost|shine|gooey|expandIcon|ringHover" }
       ]
   }

5. "tabs_feature" - Tabbed feature section (plan comparison, product categories)
   data: { "heading": "...", "badge?": "...", "tabs": [{ "label": "...", "icon?": "emoji",
     "content": { "layout": "with-image|text-only", "title": "...", "description?": "...",
       "button?": {"label","url"}, "image_url?": "..." } }] }

6. "steps_section" - Step sequence (onboarding, how-it-works)
   data: { "layout": "with-image|text-only", "steps": [{"title","description?","image_url?"}],
     "autoplay?": true, "interval?": 4000 }

7. "stats_banner" - Numeric metrics grid, text only (use RAG facts, never invent numbers)
   data: { "stats": [{"value": "10M", "label": "...", "description?": "..."}], "columns?": 2-4 }

8. "testimonial_carousel" - Quotes with optional avatar
   data: { "testimonials": [{"quote","name","role?","company?","avatar_url?"}], "autoplay?": true }

9. "pricing_cards" - Plan grid; "detailed" adds a comparison table
   data: { "variant": "compact|detailed", "plans": [{"name","price","period?","description?",
     "features": ["..."], "cta?": {"label","url"}, "highlighted?": true, "flag?": "Recommended"}] }

10. "content_grid" - Blog/news cards, per-item image-optional
   data: { "columns?": 2-4, "items": [{"layout": "with-image|text-only", "title",
     "category?", "excerpt?", "image_url?", "url?", "date?"}] }

11. "hero_banner" - Hero section
   data: { "variant": "split|centered|minimal", "headline", "subheadline?", "badge?",
     "primary_cta?": {"label","url"}, "secondary_cta?": {"label","url"}, "image_url?" }
   ("split" REQUIRES image_url; use "centered" or "minimal" without an image)

IMAGE RULE: every layout/variant "with-image" REQUIRES the matching image URL,
and that URL must come from the input. No image available? Use "text-only" /
"centered" / "minimal" - these variants are designed to look complete without images.

Guidelines:
- Use the provided context from documents to inform your answers
- **CRITICALLY IMPORTANT**: Always consider the user's profile first when crafting your response
- Adapt your language, depth, and examples based on their role and expertise level
- If you know their name, use it naturally (e.g., "Hi Marco, here's what you need to know...")
- For developers: Include technical details, code patterns, architecture considerations
- For business users: Focus on outcomes, benefits, practical applications
- For beginners: Use simpler language, more explanations, step-by-step guidance
- Select appropriate component types based on the query nature
- For factual queries, prefer text + sources
- For comparisons or data, prefer charts or bento cards
- For navigation/actions, include buttons
- Always cite sources when using retrieved information
- NEVER invent numbers: stat values, prices and chart values must be copied
  as they appear in the input (same digits, same magnitude). Numbers not
  present in the input will be removed by the system
- Set confidence based on how well the context addresses the query

PERSONALIZATION EXAMPLES:
Question: "How does authentication work?"

For a developer (role: developer):
"Let's dive into the technical implementation. Authentication typically uses JWT tokens with RS256 signing. 
Here's the flow: client sends credentials → server validates → generates JWT with payload claims → 
client stores token → subsequent requests include token in Authorization header. Consider using refresh 
tokens for security and implementing token rotation..."

For a business user (role: manager):
"Authentication ensures only authorized users can access your system. It's like a digital ID card that 
verifies who someone is before letting them in. This protects your data and ensures compliance with 
security regulations. The implementation is handled by your technical team..."
"""
    
    # Provider-neutral spec for the knowledge-base search tool
    SEARCH_TOOL = {
        "name": "search_documents",
        "description": (
            "Search the document knowledge base for relevant information. "
            "Use it when the pre-retrieved documents do not answer the "
            "user's question (e.g. a follow-up that needs a reformulated search)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "top_k": {"type": "integer", "description": "Number of results to retrieve"},
            },
            "required": ["query"],
        },
    }

    def __init__(
        self,
        model: str = None,
        vector_store=None,
        llm_client=None,
    ):
        """
        Initialize the Response Agent.

        Args:
            model: LLM model identifier
            vector_store: QdrantVectorStore instance (created if not provided)
            llm_client: LLMChatClient instance (created if not provided)
        """
        self.model = model or settings.response_model
        self.vector_store = vector_store or create_vector_store()
        self.llm = llm_client or create_llm_client(self.model)

    def _build_query_prompt(
        self,
        query: str,
        user_profile: Optional[UserProfile] = None,
        conversation_history: Optional[List[Dict]] = None,
        retrieved_context: Optional[str] = None,
    ) -> str:
        """Build the full prompt for the agent."""
        parts = []
        
        # User profile context
        if user_profile:
            parts.append(f"<user_profile>\n{user_profile.to_context()}\n</user_profile>")
        
        # Conversation history
        if conversation_history:
            history_text = "\n".join([
                f"{msg['role']}: {msg['content']}" 
                for msg in conversation_history[-5:]  # Last 5 messages
            ])
            parts.append(f"<conversation_history>\n{history_text}\n</conversation_history>")
        
        # Retrieved documents
        if retrieved_context:
            parts.append(f"<retrieved_documents>\n{retrieved_context}\n</retrieved_documents>")
        
        # The actual query
        parts.append(f"<user_query>\n{query}\n</user_query>")
        
        parts.append("\nRespond with valid JSON matching the specified structure.")
        
        return "\n\n".join(parts)
    
    def process_query(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
        tenant: Optional[str] = None,
    ) -> AgentResponse:
        """Synchronous wrapper for backward compatibility."""
        import asyncio
        return asyncio.run(
            self.process_query_async(query, user_profile, conversation_history, tenant)
        )
    
    # Deliberately NOT cached: responses depend on profile + conversation
    # history (near-zero hit rate) and caching them would replay stale
    # personalization. The expensive sub-step (vector search) is cached.
    async def process_query_async(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
        tenant: Optional[str] = None,
    ) -> AgentResponse:
        """
        Process a user query and generate a structured response asynchronously.

        Args:
            query: The user's query
            user_profile: User profile data from IndexedDB
            conversation_history: Recent conversation messages
            tenant: Tenant scope for knowledge-base retrieval

        Returns:
            AgentResponse with structured components for GenUI
        """
        # Parse user profile
        profile = UserProfile.from_dict(user_profile) if user_profile else None

        # Retrieve relevant documents asynchronously with caching
        logger.info(f"Retrieving context for query: {query[:100]}...")
        search_results = await self.vector_store.search_async(query=query, tenant=tenant)
        retrieved_context = build_context_from_results(search_results)

        # Build the full prompt
        full_prompt = self._build_query_prompt(
            query=query,
            user_profile=profile,
            conversation_history=conversation_history,
            retrieved_context=retrieved_context,
        )

        # Model-invoked searches: tenant is captured from THIS request,
        # never from shared state. Results are kept so the URL whitelist
        # also learns the URLs the tool surfaced.
        tool_contexts: List[str] = []

        async def _run_search_tool(name: str, arguments: Dict[str, Any]) -> str:
            results = await self.vector_store.search_async(
                query=str(arguments.get("query", "")),
                top_k=max(1, min(int(arguments.get("top_k") or 5), 20)),
                tenant=tenant,
            )
            context = build_context_from_results(results, include_metadata=True)
            tool_contexts.append(context)
            return context

        try:
            response_text = await self.llm.complete_json_with_tools(
                system=self.SYSTEM_PROMPT,
                user=full_prompt,
                tools=[self.SEARCH_TOOL],
                tool_handler=_run_search_tool,
            )
            logger.debug(f"Response text: {response_text[:200]}...")

            parsed = self._parse_response(response_text)

            # Extract sources from retrieval results
            sources = [
                {"title": r.metadata.get("source_document", "Unknown"), "url": r.metadata.get("url", "")}
                for r in search_results
            ]

            # Validate components against schemas; invalid ones are dropped
            valid_models, dropped = validate_components(parsed.get("components", []))
            component_dicts = [component_to_dict(c) for c in valid_models]

            # URL whitelist: only URLs that existed in the input survive
            guard = UrlGuard(enforce_whitelist=settings.url_whitelist_enabled)
            guard.allow_from_text(query)
            guard.allow_from_text(retrieved_context)
            for tool_context in tool_contexts:
                guard.allow_from_text(tool_context)
            for msg in conversation_history or []:
                guard.allow_from_text(msg.get("content"))
            for r in search_results:
                metadata = r.metadata or {}
                guard.allow(metadata.get("url"), metadata.get("image"))

            component_dicts, removed_urls = guard.sanitize_components(component_dicts)

            # Numeric grounding: displayed numbers (stats, prices, chart
            # points) must trace to the same input corpus as the URLs
            numeric_guard = NumericGuard(enforce=settings.numeric_grounding_enabled)
            numeric_guard.allow_from_text(query)
            numeric_guard.allow_from_text(retrieved_context)
            for tool_context in tool_contexts:
                numeric_guard.allow_from_text(tool_context)
            for msg in conversation_history or []:
                numeric_guard.allow_from_text(msg.get("content"))
            component_dicts, removed_numbers = numeric_guard.sanitize_components(
                component_dicts
            )

            # Per-tenant content policy: banned terms drop the component
            policy = policy_for(tenant, settings.content_policy)
            component_dicts, policy_violations = policy.sanitize_components(
                component_dicts
            )

            # The chat prose gets the same treatment as text components:
            # invented markdown links collapse, banned terms are redacted
            text_response = parsed.get("text_response", response_text)
            text_response = guard.strip_markdown_links(text_response)
            removed_urls = list(guard.removed_urls)
            text_response, text_violations = policy.redact(text_response)
            policy_violations.extend(
                t for t in text_violations if t not in policy_violations
            )

            if dropped or removed_urls or removed_numbers or policy_violations:
                logger.info(
                    "Response sanitization: dropped_components=%s removed_urls=%s "
                    "removed_numbers=%s policy_violations=%s",
                    dropped, removed_urls, removed_numbers, policy_violations,
                )

            # Model-claimed sources must pass the same URL rules
            raw_sources = parsed.get("sources", sources)
            safe_sources = [
                s for s in raw_sources
                if isinstance(s, dict) and (not s.get("url") or guard.is_allowed(s["url"]))
            ]

            return AgentResponse(
                text_response=text_response,
                components=[
                    GenUIComponent(
                        type=c["type"],
                        data=c["data"],
                        layout=c.get("layout")
                    )
                    for c in component_dicts
                ],
                sources=safe_sources,
                confidence=parsed.get("confidence", 0.5),
                suggested_actions=parsed.get("suggested_actions", []),
                sanitization={
                    "removed_urls": removed_urls,
                    "dropped_components": dropped,
                    "removed_numbers": removed_numbers,
                    "policy_violations": policy_violations,
                },
            )
            
        except Exception as e:
            logger.error(f"Agent processing failed: {e}")
            # Return a fallback response (the error stays in the logs)
            return AgentResponse(
                text_response="I couldn't process your request right now.",
                components=[
                    GenUIComponent(type="text", data={"content": "Please try rephrasing your question.", "style": "note"})
                ],
                sources=[],
                confidence=0.0,
                suggested_actions=["Rephrase question", "Contact support"],
            )
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the JSON response from the agent."""
        try:
            if isinstance(response_text, (dict, list)):
                if isinstance(response_text, list):
                    return {"components": response_text, "text_response": "", "confidence": 0.5}
                return response_text
            
            # Handle case where response might have markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            return json.loads(response_text)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            # Return a basic structure with the raw text
            return {
                "text_response": response_text,
                "components": [],
                "confidence": 0.5,
                "suggested_actions": [],
            }
        except TypeError as e:
            logger.warning(f"Type error parsing response: {e}, type: {type(response_text)}")
            if isinstance(response_text, (dict, list)):
                return response_text if isinstance(response_text, dict) else {"components": response_text}
            return {
                "text_response": str(response_text),
                "components": [],
                "confidence": 0.5,
                "suggested_actions": [],
            }


# Factory function
def create_response_agent(**kwargs) -> ResponseAgent:
    """Create a configured ResponseAgent instance."""
    return ResponseAgent(**kwargs)
