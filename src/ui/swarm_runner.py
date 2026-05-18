"""
Direct swarm runner for Streamlit UI.

This module provides a simple interface for running the swarm directly
without going through the FastAPI HTTP layer.

Now uses the LangGraph-based Orchestrator architecture.
"""

import logging
from typing import Dict, Any, Optional
from uuid import uuid4

from src.agents import Orchestrator
from src.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


class SwarmRunner:
    """
    Direct interface to the LangGraph Orchestrator for Streamlit UI.
    
    Usage:
        runner = SwarmRunner()
        result = runner.run("list all tables")
    """
    
    def __init__(self):
        """Initialize the swarm runner with LangGraph Orchestrator."""
        # Ensure agents are registered
        AgentRegistry()
        
        # Initialize the LangGraph Orchestrator
        self.orchestrator = Orchestrator()
        logger.info("LangGraph Orchestrator initialized successfully")
    
    def run(self, query: str, user_id: str = "demo_user", session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Run a query through the swarm synchronously.
        
        Args:
            query: User's query string
            user_id: ID of the user making the request
            session_id: Optional session ID for state persistence
            
        Returns:
            Dict with coordinator_response, blackboard_summary, approved_actions, etc.
        """
        if session_id is None:
            session_id = f"session_{uuid4().hex[:8]}"
        
        try:
            # Execute using the LangGraph Orchestrator
            result = self.orchestrator.run(
                user_request=query,
                history=[]  # Start with empty history
            )
            
            # Process results
            return self._process_result(result, session_id)
            
        except Exception as e:
            logger.error(f"Error running swarm: {e}", exc_info=True)
            return {
                "session_id": session_id,
                "coordinator_response": f"Error: {str(e)}",
                "blackboard_summary": {
                    "findings": [],
                    "findings_count": 0,
                    "conflicts": [],
                    "conflicts_count": 0,
                    "agent_statuses": {},
                    "execution_phase": "error"
                },
                "approved_actions": [],
                "pending_human_actions": [],
                "execution_results": {"error": str(e)}
            }
    
    def _process_result(self, result: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """
        Process the orchestrator result into a response dict.
        
        Args:
            result: Result from Orchestrator.run()
            session_id: Session ID for this run
            
        Returns:
            Processed response dict compatible with Streamlit UI
        """
        success = result.get("success", True)
        response_text = result.get("response_text", "")
        
        # Build findings from response_text if available
        findings = []
        if response_text:
            findings.append({
                "agent_id": "orchestrator",
                "success": success,
                "summary": response_text,
                "output": {},
                "error": None
            })
        
        # Determine execution phase and agent status
        agent_statuses = {"orchestrator": "completed"} if success else {"orchestrator": "failed"}
        execution_phase = "completed" if success else "error"
        
        # Build blackboard summary
        blackboard_summary = {
            "findings": findings,
            "findings_count": len(findings),
            "conflicts": [],
            "conflicts_count": 0,
            "agent_statuses": agent_statuses,
            "execution_phase": execution_phase
        }
        
        return {
            "session_id": session_id,
            "coordinator_response": response_text,
            "blackboard_summary": blackboard_summary,
            "approved_actions": [],
            "pending_human_actions": [],
            "execution_results": {
                "success": success
            }
        }


def get_swarm_runner() -> SwarmRunner:
    """Get a singleton swarm runner instance."""
    if not hasattr(get_swarm_runner, '_instance'):
        get_swarm_runner._instance = SwarmRunner()
    return get_swarm_runner._instance