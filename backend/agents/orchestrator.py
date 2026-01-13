"""
Agent Orchestrator Module
Coordinates the Response Agent, Profile Agent, and Behave Agent for unified query processing.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .response_agent import ResponseAgent, AgentResponse, create_response_agent
from .profile_agent import ProfileAgent, ProfileAnalysisResult, create_profile_agent
from .behave_agent import BehaveAgent, BehaviorAnalysisResult, create_behave_agent

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Combined result from all agents."""
    response: AgentResponse
    profile_analysis: ProfileAnalysisResult
    behavior_analysis: Optional[BehaviorAnalysisResult]
    updated_profile: Optional[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "response": self.response.to_dict(),
            "profile_analysis": self.profile_analysis.to_dict(),
            "updated_profile": self.updated_profile,
        }
        if self.behavior_analysis:
            result["behavior_analysis"] = self.behavior_analysis.to_dict()
        return result
    
    def to_frontend_response(self) -> Dict[str, Any]:
        """
        Format for frontend consumption.
        Includes only what the frontend needs.
        """
        # Combine profile updates from both Profile Agent and Behave Agent
        all_updates = [u.to_dict() for u in self.profile_analysis.updates]
        
        if self.behavior_analysis:
            # Add behavior-derived updates with "behavior." prefix
            for update in self.behavior_analysis.profile_updates:
                # Ensure behavior updates have proper field naming
                field = update.get("field", "")
                if not field.startswith("behavior."):
                    update["field"] = f"behavior.{field}"
                all_updates.append(update)
        
        should_update = self.profile_analysis.has_profile_info or (
            self.behavior_analysis and len(self.behavior_analysis.profile_updates) > 0
        )
        
        response = {
            # Main response content
            "text": self.response.text_response,
            "components": [c.to_dict() for c in self.response.components],
            "sources": self.response.sources,
            "suggested_actions": self.response.suggested_actions,
            
            # Profile update instructions for IndexedDB
            "profile_updates": {
                "should_update": should_update,
                "updates": all_updates,
            },
            
            # Metadata
            "meta": {
                "confidence": self.response.confidence,
                "interaction_type": self.profile_analysis.interaction_type,
                "topics": self.profile_analysis.topics,
                "sentiment": self.profile_analysis.sentiment,
            }
        }
        
        # Add behavior insights to meta if available
        if self.behavior_analysis:
            response["meta"]["behavior"] = {
                "engagement_score": self.behavior_analysis.engagement_score,
                "user_type": self.behavior_analysis.user_type,
                "session_summary": self.behavior_analysis.session_summary,
                "insights_count": len(self.behavior_analysis.insights),
                "ui_adjustments": self.behavior_analysis.recommended_ui_adjustments,
            }
        
        return response


class AgentOrchestrator:
    """
    Orchestrates the multi-agent system for GenUI.
    
    Coordinates:
    - Response Agent: Handles query answering with RAG
    - Profile Agent: Extracts profile information from queries
    - Behave Agent: Analyzes user behavior patterns
    
    All agents run in parallel for efficiency.
    """
    
    def __init__(
        self,
        response_agent: Optional[ResponseAgent] = None,
        profile_agent: Optional[ProfileAgent] = None,
        behave_agent: Optional[BehaveAgent] = None,
        parallel_execution: bool = True,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            response_agent: Pre-configured ResponseAgent (created if not provided)
            profile_agent: Pre-configured ProfileAgent (created if not provided)
            behave_agent: Pre-configured BehaveAgent (created if not provided)
            parallel_execution: Whether to run agents in parallel
        """
        self.response_agent = response_agent or create_response_agent()
        self.profile_agent = profile_agent or create_profile_agent()
        self.behave_agent = behave_agent or create_behave_agent()
        self.parallel_execution = parallel_execution
    
    async def process(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
        behavior_data: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        Process a user query through all agents asynchronously.
        
        Args:
            query: The user's query
            user_profile: Current user profile from IndexedDB
            conversation_history: Recent conversation messages
            behavior_data: User behavior data from BehaviorTracker
            
        Returns:
            OrchestratorResult with combined agent outputs
        """
        if self.parallel_execution:
            return await self._process_parallel_async(query, user_profile, conversation_history, behavior_data)
        else:
            return await self._process_sequential_async(query, user_profile, conversation_history, behavior_data)
    
    def process_sync(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
        behavior_data: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """Synchronous wrapper for backwards compatibility."""
        return asyncio.run(self.process(query, user_profile, conversation_history, behavior_data))
    
    async def _process_parallel_async(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]],
        conversation_history: Optional[List[Dict]],
        behavior_data: Optional[Dict[str, Any]],
    ) -> OrchestratorResult:
        """Run all agents in parallel using asyncio.gather for true async concurrency."""
        
        # Create coroutines for each agent
        response_task = self.response_agent.process_query_async(
            query,
            user_profile,
            conversation_history,
        )
        
        profile_task = self.profile_agent.analyze_message_async(
            query,
            conversation_history,
        )
        
        # Gather all tasks to run in parallel
        if behavior_data:
            behavior_task = self.behave_agent.analyze_behavior_async(
                behavior_data,
                user_profile,
            )
            response_result, profile_result, behavior_result = await asyncio.gather(
                response_task,
                profile_task,
                behavior_task,
            )
        else:
            response_result, profile_result = await asyncio.gather(
                response_task,
                profile_task,
            )
            behavior_result = None
        
        # Merge all profile updates
        updated_profile = self._merge_all_updates(
            user_profile,
            profile_result,
            behavior_result,
        )
        
        return OrchestratorResult(
            response=response_result,
            profile_analysis=profile_result,
            behavior_analysis=behavior_result,
            updated_profile=updated_profile,
        )
    
    async def _process_sequential_async(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]],
        conversation_history: Optional[List[Dict]],
        behavior_data: Optional[Dict[str, Any]],
    ) -> OrchestratorResult:
        """Run agents sequentially (for debugging or low-resource environments)."""
        
        # Run response agent first
        response_result = await self.response_agent.process_query_async(
            query,
            user_profile,
            conversation_history,
        )
        
        # Then profile agent
        profile_result = await self.profile_agent.analyze_message_async(
            query,
            conversation_history,
        )
        
        # Then behavior agent if we have data
        behavior_result = None
        if behavior_data:
            behavior_result = await self.behave_agent.analyze_behavior_async(
                behavior_data,
                user_profile,
            )
        
        # Merge all profile updates
        updated_profile = self._merge_all_updates(
            user_profile,
            profile_result,
            behavior_result,
        )
        
        return OrchestratorResult(
            response=response_result,
            profile_analysis=profile_result,
            behavior_analysis=behavior_result,
            updated_profile=updated_profile,
        )
    
    def _merge_all_updates(
        self,
        user_profile: Optional[Dict[str, Any]],
        profile_result: ProfileAnalysisResult,
        behavior_result: Optional[BehaviorAnalysisResult],
    ) -> Optional[Dict[str, Any]]:
        """Merge profile updates from all sources."""
        if user_profile is None:
            return None
        
        has_updates = profile_result.has_profile_info or (
            behavior_result and len(behavior_result.profile_updates) > 0
        )
        
        if not has_updates:
            return None
        
        # Start with profile agent updates
        updated_profile = user_profile.copy()
        
        if profile_result.has_profile_info:
            updated_profile = self.profile_agent.merge_profile_updates(
                updated_profile,
                profile_result.updates,
            )
        
        # Add behavior agent updates
        if behavior_result and behavior_result.profile_updates:
            updated_profile = self._apply_behavior_updates(
                updated_profile,
                behavior_result,
            )
        
        return updated_profile
    
    def _apply_behavior_updates(
        self,
        profile: Dict[str, Any],
        behavior_result: BehaviorAnalysisResult,
    ) -> Dict[str, Any]:
        """Apply behavior-derived updates to profile."""
        if "behavior" not in profile:
            profile["behavior"] = {}
        
        # Apply individual updates
        for update in behavior_result.profile_updates:
            field = update.get("field", "")
            value = update.get("value")
            confidence = update.get("confidence", 0.5)
            
            # Remove "behavior." prefix if present
            if field.startswith("behavior."):
                field = field[9:]
            
            # Only apply if confidence is high enough
            if confidence >= 0.5 and field and value is not None:
                profile["behavior"][field] = {
                    "value": value,
                    "confidence": confidence,
                    "updated_at": None,  # Will be set by frontend
                }
        
        # Store aggregated behavior metrics
        profile["behavior"]["_engagement_score"] = behavior_result.engagement_score
        profile["behavior"]["_user_type"] = behavior_result.user_type
        profile["behavior"]["_last_analysis"] = behavior_result.session_summary
        
        return profile
    
    async def process_async(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None,
        behavior_data: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        Async version of process for use with FastAPI.
        """
        loop = asyncio.get_event_loop()
        
        # Run in thread pool to not block the event loop
        result = await loop.run_in_executor(
            self._executor,
            lambda: self.process(query, user_profile, conversation_history, behavior_data),
        )
        
        return result
    
    def __del__(self):
        """Cleanup thread pool on deletion."""
        self._executor.shutdown(wait=False)


# Factory function
def create_orchestrator(**kwargs) -> AgentOrchestrator:
    """Create a configured AgentOrchestrator instance."""
    return AgentOrchestrator(**kwargs)


# Convenience singleton for simple usage
_default_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the default orchestrator instance."""
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = create_orchestrator()
    return _default_orchestrator