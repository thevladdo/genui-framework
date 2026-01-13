"""
Profile Agent Module
Analyzes user queries to extract relevant profile information.
Determines what user data should be stored in IndexedDB.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient

from config import settings
from utils.cache import cacheable

logger = logging.getLogger(__name__)


@dataclass
class ProfileUpdate:
    """Represents a suggested update to the user profile."""
    field: str
    value: Any
    confidence: float
    source: str  # The query/statement that led to this insight
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass
class ProfileAnalysisResult:
    """Result of profile analysis on a user message."""
    has_profile_info: bool
    updates: List[ProfileUpdate]
    interaction_type: str  # "question", "statement", "command", "feedback"
    topics: List[str]
    sentiment: str  # "positive", "neutral", "negative"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_profile_info": self.has_profile_info,
            "updates": [u.to_dict() for u in self.updates],
            "interaction_type": self.interaction_type,
            "topics": self.topics,
            "sentiment": self.sentiment,
        }


class ProfileAgent:
    """
    Agent responsible for analyzing user messages to extract profile information.
    
    This agent runs in parallel with the Response Agent and determines
    what information should be persisted to the user's profile in IndexedDB.
    """
    
    SYSTEM_PROMPT = """You are a profile analysis agent. Your job is to analyze user messages 
and extract any relevant information that could be useful for personalizing future interactions.

You MUST respond with valid JSON in this exact structure:
{
    "has_profile_info": true/false,
    "updates": [
        {
            "field": "preference.category|interest.topic|context.situation|demographic.info",
            "value": "the extracted value",
            "confidence": 0.0-1.0
        }
    ],
    "interaction_type": "question|statement|command|feedback",
    "topics": ["topic1", "topic2"],
    "sentiment": "positive|neutral|negative"
}

Profile field categories:
- preference.*: User preferences (e.g., preference.communication_style, preference.detail_level)
- interest.*: Topics of interest (e.g., interest.technology, interest.sports)
- context.*: Current context/situation (e.g., context.current_project, context.deadline)
- demographic.*: Demographic info shared explicitly (e.g., demographic.role, demographic.industry)
- behavior.*: Observed behavior patterns (e.g., behavior.asks_follow_ups, behavior.prefers_examples)

Guidelines:
1. Only extract information that is explicitly stated or strongly implied
2. Do NOT infer demographic information unless explicitly stated
3. Preferences should be actionable (how to adjust responses)
4. Context is temporary; interests and preferences are persistent
5. Set confidence based on how explicit the information is:
   - 0.9+: Directly stated ("I prefer...", "I work in...")
   - 0.7-0.9: Strongly implied ("As a developer..." implies developer role)
   - 0.5-0.7: Reasonably inferred (topic focus suggests interest)
   - <0.5: Don't include, too speculative
6. If no profile-relevant info, return has_profile_info: false with empty updates

Examples:

User: "I'm a software engineer working on a machine learning project"
→ has_profile_info: true
→ updates: [
    {"field": "demographic.role", "value": "software engineer", "confidence": 0.95},
    {"field": "context.current_project", "value": "machine learning project", "confidence": 0.9}
]

User: "What's the weather like today?"
→ has_profile_info: false
→ updates: []

User: "Can you explain this more simply? The technical jargon is confusing."
→ has_profile_info: true
→ updates: [
    {"field": "preference.detail_level", "value": "simple", "confidence": 0.85},
    {"field": "preference.technical_jargon", "value": "avoid", "confidence": 0.8}
]
"""
    
    def __init__(self, model: str = None):
        """
        Initialize the Profile Agent.
        
        Args:
            model: LLM model identifier (uses a smaller/faster model by default)
        """
        self.model = model or settings.profile_model
        
        self.client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=self.model,
        )
        
        # Create the agent
        self.agent = Agent(
            name="profile_agent",
            client=self.client,
            system_prompt=self.SYSTEM_PROMPT,
        )
    
    def analyze_message(
        self,
        message: str,
        conversation_context: Optional[List[Dict]] = None,
    ) -> ProfileAnalysisResult:
        """Synchronous wrapper for backward compatibility."""
        import asyncio
        return asyncio.run(self.analyze_message_async(message, conversation_context))
    
    @cacheable()
    async def analyze_message_async(
        self,
        message: str,
        conversation_context: Optional[List[Dict]] = None,
    ) -> ProfileAnalysisResult:
        """
        Analyze a user message for profile-relevant information asynchronously.
        
        Args:
            message: The user's message to analyze
            conversation_context: Recent conversation for context
            
        Returns:
            ProfileAnalysisResult with extracted profile updates
        """
        # Build the analysis prompt
        prompt_parts = []
        
        if conversation_context:
            context_text = "\n".join([
                f"{msg['role']}: {msg['content'][:200]}"  # Truncate long messages
                for msg in conversation_context[-3:]  # Last 3 messages
            ])
            prompt_parts.append(f"<conversation_context>\n{context_text}\n</conversation_context>")
        
        prompt_parts.append(f"<message_to_analyze>\n{message}\n</message_to_analyze>")
        prompt_parts.append("\nAnalyze this message and respond with valid JSON.")
        
        full_prompt = "\n\n".join(prompt_parts)
        
        try:
            # Use async a_run instead of run
            response = await self.agent.a_run(full_prompt)
            
            # Extract text from response - handle different response formats
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, str):
                    response_text = content
                elif isinstance(content, list):
                    # Extract text from list of content blocks
                    response_text = ""
                    for block in content:
                        if hasattr(block, 'text'):
                            response_text += block.text
                        elif hasattr(block, 'content'):
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
            
            # Clean up TextBlock wrapper if present
            if response_text.startswith('TextBlock(content='):
                start = response_text.find('{')
                end = response_text.rfind('}')
                if start != -1 and end != -1:
                    response_text = response_text[start:end+1]
            
            # Parse the JSON response
            parsed = self._parse_response(response_text)
            
            # Convert to ProfileAnalysisResult
            updates = [
                ProfileUpdate(
                    field=u["field"],
                    value=u["value"],
                    confidence=u.get("confidence", 0.5),
                    source=message[:100],  # Truncate source
                )
                for u in parsed.get("updates", [])
                if u.get("confidence", 0) >= 0.5  # Filter low-confidence updates
            ]
            
            return ProfileAnalysisResult(
                has_profile_info=parsed.get("has_profile_info", False) and len(updates) > 0,
                updates=updates,
                interaction_type=parsed.get("interaction_type", "question"),
                topics=parsed.get("topics", []),
                sentiment=parsed.get("sentiment", "neutral"),
            )
            
        except Exception as e:
            logger.error(f"Profile analysis failed: {e}")
            # Return empty result on failure
            return ProfileAnalysisResult(
                has_profile_info=False,
                updates=[],
                interaction_type="question",
                topics=[],
                sentiment="neutral",
            )
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from the agent."""
        try:
            # If already a dict or list, return it
            if isinstance(response_text, dict):
                return response_text
            if isinstance(response_text, list):
                return {"has_profile_info": False, "updates": []}
            
            # Handle markdown code blocks
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
            logger.warning(f"Failed to parse profile analysis JSON: {e}")
            return {"has_profile_info": False, "updates": []}
    
    def merge_profile_updates(
        self,
        existing_profile: Dict[str, Any],
        new_updates: List[ProfileUpdate],
    ) -> Dict[str, Any]:
        """
        Merge new profile updates with existing profile data.
        
        Uses confidence scores to decide whether to update existing values.
        
        Args:
            existing_profile: Current user profile
            new_updates: New updates to merge
            
        Returns:
            Updated profile dictionary
        """
        profile = existing_profile.copy()
        
        for update in new_updates:
            # Parse the field path (e.g., "preference.detail_level")
            parts = update.field.split(".")
            
            if len(parts) != 2:
                logger.warning(f"Invalid field format: {update.field}")
                continue
            
            category, key = parts
            
            # Ensure category exists
            if category not in profile:
                profile[category] = {}
            
            # Check if we should update (higher confidence wins)
            existing_entry = profile[category].get(key)
            
            if existing_entry is None:
                # New field, add it
                profile[category][key] = {
                    "value": update.value,
                    "confidence": update.confidence,
                    "updated_at": update.timestamp,
                }
            elif isinstance(existing_entry, dict):
                # Update only if new confidence is higher
                if update.confidence > existing_entry.get("confidence", 0):
                    profile[category][key] = {
                        "value": update.value,
                        "confidence": update.confidence,
                        "updated_at": update.timestamp,
                    }
            else:
                # Legacy format, overwrite
                profile[category][key] = {
                    "value": update.value,
                    "confidence": update.confidence,
                    "updated_at": update.timestamp,
                }
        
        return profile


# Factory function
def create_profile_agent(**kwargs) -> ProfileAgent:
    """Create a configured ProfileAgent instance."""
    return ProfileAgent(**kwargs)
