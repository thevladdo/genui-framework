"""
Behave Agent Module
Analyzes user behavior data to extract insights and profile updates.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient

from config import settings
from utils.cache import cacheable

logger = logging.getLogger(__name__)


@dataclass
class BehaviorInsight:
    """A single insight derived from behavior analysis."""
    category: str  # e.g., "navigation_preference", "content_interest", "interaction_style"
    key: str
    value: Any
    confidence: float
    evidence: str  # Brief explanation of what behavior led to this insight


@dataclass
class BehaviorAnalysisResult:
    """Result of behavior analysis."""
    insights: List[BehaviorInsight]
    profile_updates: List[Dict[str, Any]]
    engagement_score: float  # 0-1 indicating user engagement level
    user_type: str  # e.g., "explorer", "focused", "scanner", "deep_reader"
    session_summary: str
    recommended_ui_adjustments: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "insights": [
                {
                    "category": i.category,
                    "key": i.key,
                    "value": i.value,
                    "confidence": i.confidence,
                    "evidence": i.evidence,
                }
                for i in self.insights
            ],
            "profile_updates": self.profile_updates,
            "engagement_score": self.engagement_score,
            "user_type": self.user_type,
            "session_summary": self.session_summary,
            "recommended_ui_adjustments": self.recommended_ui_adjustments,
        }


class BehaveAgent:
    """
    Agent responsible for analyzing user behavior patterns.
    
    Examines click patterns, scroll behavior, navigation paths, and
    interaction timing to derive insights about user preferences and needs.
    """
    
    SYSTEM_PROMPT = """You are a behavioral analysis expert specializing in user experience patterns.
Your task is to analyze user behavior data and extract meaningful insights that can improve their experience.

You will receive behavior data including:
- Click events with positions and targets
- Scroll patterns and depth
- Page visit history and duration
- Hover events on interactive elements
- Element interactions
- Heatmap zone distribution
- Navigation paths

Based on this data, you must output valid JSON with this structure:
{
    "insights": [
        {
            "category": "category_name",
            "key": "specific_key",
            "value": "derived_value",
            "confidence": 0.0-1.0,
            "evidence": "Brief explanation of behavior that led to this insight"
        }
    ],
    "profile_updates": [
        {
            "field": "behavior.field_name",
            "value": "value",
            "confidence": 0.0-1.0
        }
    ],
    "engagement_score": 0.0-1.0,
    "user_type": "explorer|focused|scanner|deep_reader|casual",
    "session_summary": "Brief summary of user behavior this session",
    "recommended_ui_adjustments": [
        {
            "type": "adjustment_type",
            "target": "what_to_adjust",
            "suggestion": "specific_suggestion"
        }
    ]
}

Categories for insights:
- "navigation_preference": How user prefers to navigate (menu, search, direct links)
- "content_interest": Topics or content types user engages with most
- "interaction_style": How user interacts (clicks vs hovers, fast vs deliberate)
- "attention_pattern": Where user focuses attention on page
- "pace_preference": Speed of browsing (quick scan vs thorough reading)
- "device_behavior": Patterns suggesting device/context usage

User types:
- "explorer": Clicks widely, visits many pages, curious behavior
- "focused": Goes directly to target, minimal exploration
- "scanner": Quick scrolls, brief hovers, skims content
- "deep_reader": Long page times, thorough scrolling, engaged reading
- "casual": Irregular patterns, distracted behavior

UI adjustment types:
- "layout": Suggestions for layout changes
- "navigation": Navigation structure adjustments
- "content_density": More/less content per view
- "interaction_feedback": Enhanced or reduced feedback on interactions
- "component_preference": Preferred component types (cards, lists, etc.)

Guidelines:
- Only report insights with confidence >= 0.5
- Base insights on actual behavior patterns, not assumptions
- Consider session duration when assessing engagement
- Look for repeated patterns, not single events
- Recommend UI adjustments that would improve this user's experience
- Be conservative with profile updates - only update when confident
"""
    
    def __init__(self, model: str = None):
        """
        Initialize the Behave Agent.
        
        Args:
            model: LLM model identifier (defaults to profile_model from settings)
        """
        self.model = model or settings.profile_model
        
        self.client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=self.model,
        )
        
        # Create the agent
        self.agent = Agent(
            name="behave_agent",
            client=self.client,
            system_prompt=self.SYSTEM_PROMPT,
        )
    
    def analyze_behavior(
        self,
        behavior_data: Dict[str, Any],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> BehaviorAnalysisResult:
        """Synchronous wrapper for backward compatibility."""
        import asyncio
        return asyncio.run(self.analyze_behavior_async(behavior_data, user_profile))
    
    @cacheable()
    async def analyze_behavior_async(
        self,
        behavior_data: Dict[str, Any],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> BehaviorAnalysisResult:
        """
        Analyze user behavior data and extract insights asynchronously.
        
        Args:
            behavior_data: Compact behavior summary from frontend
            user_profile: Current user profile for context
            
        Returns:
            BehaviorAnalysisResult with insights and profile updates
        """
        if not behavior_data:
            return self._empty_result()
        
        # Build the analysis prompt
        prompt = self._build_analysis_prompt(behavior_data, user_profile)
        
        try:
            # Use async a_run instead of run
            response = await self.agent.a_run(prompt)
            
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
            
            # Parse JSON response
            parsed = self._parse_response(response_text)
            
            return BehaviorAnalysisResult(
                insights=[
                    BehaviorInsight(
                        category=i.get("category", "unknown"),
                        key=i.get("key", ""),
                        value=i.get("value"),
                        confidence=i.get("confidence", 0.5),
                        evidence=i.get("evidence", ""),
                    )
                    for i in parsed.get("insights", [])
                    if i.get("confidence", 0) >= 0.5
                ],
                profile_updates=parsed.get("profile_updates", []),
                engagement_score=parsed.get("engagement_score", 0.5),
                user_type=parsed.get("user_type", "casual"),
                session_summary=parsed.get("session_summary", ""),
                recommended_ui_adjustments=parsed.get("recommended_ui_adjustments", []),
            )
            
        except Exception as e:
            logger.error(f"Behavior analysis failed: {e}")
            return self._empty_result()
    
    def _build_analysis_prompt(
        self,
        behavior_data: Dict[str, Any],
        user_profile: Optional[Dict[str, Any]],
    ) -> str:
        """Build the prompt for behavior analysis."""
        parts = []
        
        # Include user profile context if available
        if user_profile:
            profile_summary = self._summarize_profile(user_profile)
            parts.append(f"<existing_profile>\n{profile_summary}\n</existing_profile>")
        
        # Format behavior data
        behavior_summary = self._format_behavior_data(behavior_data)
        parts.append(f"<behavior_data>\n{behavior_summary}\n</behavior_data>")
        
        parts.append("\nAnalyze this behavior data and respond with valid JSON matching the specified structure.")
        
        return "\n\n".join(parts)
    
    def _format_behavior_data(self, data: Dict[str, Any]) -> str:
        """Format behavior data for the prompt."""
        lines = []
        
        # Session info
        duration_sec = data.get("duration", 0) / 1000
        lines.append(f"Session Duration: {duration_sec:.1f} seconds")
        lines.append(f"Total Clicks: {data.get('clickCount', 0)}")
        lines.append(f"Max Scroll Depth: {data.get('maxScrollDepth', 0)}%")
        lines.append(f"Pages Visited: {data.get('pagesVisited', 0)}")
        
        # Heatmap zones
        heatmap = data.get("heatmapZones", [])
        if heatmap:
            lines.append("\nClick Heatmap Distribution:")
            for zone in heatmap[:5]:  # Top 5 zones
                lines.append(f"  - {zone.get('zone', 'unknown')}: {zone.get('count', 0)} clicks")
        
        # Navigation path
        nav_path = data.get("navigationPath", [])
        if nav_path:
            lines.append(f"\nNavigation Path: {' → '.join(nav_path[-10:])}")
        
        # Recent clicks
        recent_clicks = data.get("recentClicks", [])
        if recent_clicks:
            lines.append("\nRecent Click Targets:")
            for click in recent_clicks[-5:]:
                target = click.get("target", "unknown")
                target_id = click.get("targetId", "")
                lines.append(f"  - {target}" + (f"#{target_id}" if target_id else ""))
        
        # Recent interactions
        interactions = data.get("recentInteractions", [])
        if interactions:
            lines.append("\nElement Interactions:")
            for inter in interactions[-10:]:
                lines.append(f"  - {inter.get('interactionType', 'unknown')} on {inter.get('elementType', 'unknown')} ({inter.get('elementId', 'no-id')})")
        
        return "\n".join(lines)
    
    def _summarize_profile(self, profile: Dict[str, Any]) -> str:
        """Create a brief summary of existing profile."""
        parts = []
        
        if profile.get("preferences"):
            prefs = profile["preferences"]
            if isinstance(prefs, dict):
                pref_items = [f"{k}: {v}" for k, v in list(prefs.items())[:5]]
                parts.append(f"Known Preferences: {', '.join(pref_items)}")
        
        if profile.get("behavior"):
            behavior = profile["behavior"]
            if isinstance(behavior, dict):
                behav_items = [f"{k}: {v}" for k, v in list(behavior.items())[:5]]
                parts.append(f"Known Behaviors: {', '.join(behav_items)}")
        
        return "\n".join(parts) if parts else "No existing profile data."
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the JSON response from the agent."""
        try:
            # If already a dict or list, return it
            if isinstance(response_text, dict):
                return response_text
            if isinstance(response_text, list):
                return {}
            
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
            logger.warning(f"Failed to parse behavior analysis response: {e}")
            return {}
    
    def _empty_result(self) -> BehaviorAnalysisResult:
        """Return an empty result when analysis cannot be performed."""
        return BehaviorAnalysisResult(
            insights=[],
            profile_updates=[],
            engagement_score=0.5,
            user_type="casual",
            session_summary="Insufficient behavior data for analysis.",
            recommended_ui_adjustments=[],
        )
    
    def quick_analyze(self, behavior_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a quick heuristic analysis without LLM.
        Useful for real-time feedback or when LLM is unavailable.
        
        Returns basic insights based on simple rules.
        """
        if not behavior_data:
            return {"engagement_score": 0.5, "user_type": "casual"}
        
        duration = behavior_data.get("duration", 0) / 1000  # Convert to seconds
        clicks = behavior_data.get("clickCount", 0)
        scroll_depth = behavior_data.get("maxScrollDepth", 0)
        pages = behavior_data.get("pagesVisited", 0)
        
        # Calculate engagement score
        engagement = 0.0
        if duration > 30:
            engagement += 0.2
        if duration > 120:
            engagement += 0.2
        if clicks > 5:
            engagement += 0.2
        if scroll_depth > 50:
            engagement += 0.2
        if pages > 2:
            engagement += 0.2
        
        # Determine user type
        user_type = "casual"
        if pages > 5 and clicks > 10:
            user_type = "explorer"
        elif scroll_depth > 80 and duration > 60:
            user_type = "deep_reader"
        elif clicks > 15 and duration < 60:
            user_type = "scanner"
        elif pages <= 2 and scroll_depth > 50:
            user_type = "focused"
        
        # Determine attention pattern from heatmap
        heatmap = behavior_data.get("heatmapZones", [])
        attention_pattern = "balanced"
        if heatmap:
            top_zone = heatmap[0].get("zone", "") if heatmap else ""
            if "top" in top_zone:
                attention_pattern = "top-focused"
            elif "middle" in top_zone:
                attention_pattern = "center-focused"
            elif "bottom" in top_zone:
                attention_pattern = "bottom-focused"
        
        return {
            "engagement_score": min(engagement, 1.0),
            "user_type": user_type,
            "attention_pattern": attention_pattern,
            "metrics": {
                "duration_seconds": duration,
                "click_count": clicks,
                "scroll_depth": scroll_depth,
                "pages_visited": pages,
            },
        }


# Factory function
def create_behave_agent(**kwargs) -> BehaveAgent:
    """Create a configured BehaveAgent instance."""
    return BehaveAgent(**kwargs)