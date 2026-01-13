"""
Response Agent Module
Handles user queries using RAG retrieval and user profile context.
Generates structured responses suitable for GenUI rendering.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient
from datapizza.tools import tool

from config import settings
from rag import create_vector_store, build_context_from_results
from utils.cache import cacheable

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
                parts.append(f"User Demographics:\n- " + "\n- ".join(demo_items))
        
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
                parts.append(f"User Interests:\n- " + "\n- ".join(interest_items))
        
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
                parts.append(f"User Preferences:\n- " + "\n- ".join(pref_items))
        
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
                parts.append(f"Observed Behavior:\n- " + "\n- ".join(behavior_items))
        
        if self.history_summary:
            parts.append(f"Interaction History: {self.history_summary}")
        
        return "\n\n".join(parts) if parts else "No user profile available."


@dataclass 
class GenUIComponent:
    """Structured component for frontend rendering."""
    type: str  # "bento", "chart", "text", "buttons"
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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_response": self.text_response,
            "components": [c.to_dict() for c in self.components],
            "sources": self.sources,
            "confidence": self.confidence,
            "suggested_actions": self.suggested_actions,
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
            "type": "text|bento|chart|buttons",
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
       "chart_type": "bar|line|pie|area",
       "title": "Chart Title",
       "data": [{ "label": "...", "value": ... }],
       "x_axis": "...",
       "y_axis": "..."
   }

4. "buttons" - Action buttons with links
   data: {
       "buttons": [
           { "label": "...", "url": "...", "style": "primary|secondary|outline" }
       ]
   }

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
- Set confidence based on how well the context addresses the query

PERSONALIZATION EXAMPLES:
Question: "How does authentication work?"

For a developer (role: sviluppatore):
"Let's dive into the technical implementation. Authentication typically uses JWT tokens with RS256 signing. 
Here's the flow: client sends credentials → server validates → generates JWT with payload claims → 
client stores token → subsequent requests include token in Authorization header. Consider using refresh 
tokens for security and implementing token rotation..."

For a business user (role: manager):
"Authentication ensures only authorized users can access your system. It's like a digital ID card that 
verifies who someone is before letting them in. This protects your data and ensures compliance with 
security regulations. The implementation is handled by your technical team..."
"""
    
    def __init__(
        self,
        model: str = None,
        vector_store=None,
    ):
        """
        Initialize the Response Agent.
        
        Args:
            model: LLM model identifier
            vector_store: QdrantVectorStore instance (created if not provided)
        """
        self.model = model or settings.response_model
        self.vector_store = vector_store or create_vector_store()
        
        self.client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=self.model,
        )
        
        # Create the agent with tools and streaming support
        self.agent = Agent(
            name="response_agent",
            client=self.client,
            system_prompt=self.SYSTEM_PROMPT,
            tools=[self._search_documents],
            stream=True,  # Enable streaming for faster feedback
        )
    
    @tool
    def _search_documents(self, query: str, top_k: int = 5) -> str:
        """
        Search the document knowledge base for relevant information.
        
        Args:
            query: The search query
            top_k: Number of results to retrieve
        """
        results = self.vector_store.search(query=query, top_k=top_k)
        return build_context_from_results(results, include_metadata=True)
    
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
    ) -> AgentResponse:
        """Synchronous wrapper for backward compatibility."""
        import asyncio
        return asyncio.run(self.process_query_async(query, user_profile, conversation_history))
    
    @cacheable()
    async def process_query_async(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> AgentResponse:
        """
        Process a user query and generate a structured response asynchronously.
        
        Args:
            query: The user's query
            user_profile: User profile data from IndexedDB
            conversation_history: Recent conversation messages
            
        Returns:
            AgentResponse with structured components for GenUI
        """
        # Parse user profile
        profile = UserProfile.from_dict(user_profile) if user_profile else None
        
        # Retrieve relevant documents asynchronously with caching
        logger.info(f"Retrieving context for query: {query[:100]}...")
        search_results = await self.vector_store.search_async(query=query)
        retrieved_context = build_context_from_results(search_results)
        
        # Build the full prompt
        full_prompt = self._build_query_prompt(
            query=query,
            user_profile=profile,
            conversation_history=conversation_history,
            retrieved_context=retrieved_context,
        )
        
        # Run the agent using async a_run
        try:
            response = await self.agent.a_run(full_prompt)
            
            # Extract text from response - handle different response formats
            if hasattr(response, 'content'):
                # response.content might be a string, list of TextBlocks, or other format
                content = response.content
                if isinstance(content, str):
                    response_text = content
                elif isinstance(content, list):
                    # Extract text from list of content blocks (e.g., Anthropic's format)
                    response_text = ""
                    for block in content:
                        if hasattr(block, 'text'):
                            response_text += block.text
                        elif hasattr(block, 'content'):
                            # Some blocks have nested content
                            response_text += str(block.content)
                        elif isinstance(block, dict) and 'text' in block:
                            response_text += block['text']
                        elif isinstance(block, dict) and 'content' in block:
                            response_text += str(block['content'])
                        else:
                            response_text += str(block)
                else:
                    response_text = str(content)
            else:
                response_text = str(response)
            
            # Clean up the response text - remove "TextBlock(content=" wrapper if present
            if response_text.startswith('TextBlock(content='):
                # Extract the actual content from TextBlock wrapper
                start = response_text.find('{')
                end = response_text.rfind('}')
                if start != -1 and end != -1:
                    response_text = response_text[start:end+1]
            
            logger.debug(f"Extracted response text: {response_text[:200]}...")
            
            # Parse JSON response
            parsed = self._parse_response(response_text)
            
            # Extract sources from retrieval results
            sources = [
                {"title": r.metadata.get("source_document", "Unknown"), "url": r.metadata.get("url", "")}
                for r in search_results
            ]
            
            return AgentResponse(
                text_response=parsed.get("text_response", response_text),
                components=[
                    GenUIComponent(
                        type=c["type"],
                        data=c["data"],
                        layout=c.get("layout")
                    )
                    for c in parsed.get("components", [])
                ],
                sources=parsed.get("sources", sources),
                confidence=parsed.get("confidence", 0.5),
                suggested_actions=parsed.get("suggested_actions", []),
            )
            
        except Exception as e:
            logger.error(f"Agent processing failed: {e}")
            # Return a fallback response
            return AgentResponse(
                text_response=f"I encountered an issue processing your request: {str(e)}",
                components=[
                    GenUIComponent(type="text", data={"content": "Please try rephrasing your question.", "style": "note"})
                ],
                sources=[],
                confidence=0.0,
                suggested_actions=["Rephrase question", "Contact support"],
            )
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the JSON response from the agent."""
        # Try to extract JSON from the response
        try:
            # If response_text is already a dict or list, return it directly
            if isinstance(response_text, (dict, list)):
                if isinstance(response_text, list):
                    # If it's a list, wrap it in a dict
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
            # If we get a type error, try to handle it gracefully
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
