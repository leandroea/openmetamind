"""
Direct swarm runner for Streamlit UI.

This module provides a simple interface for running the swarm directly
without going through the FastAPI HTTP layer.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from uuid import uuid4

from src.graph.swarm_graph import build_swarm_graph
from src.models.state import SwarmState
from src.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


class SwarmRunner:
    """
    Direct interface to the swarm graph for Streamlit UI.
    
    Usage:
        runner = SwarmRunner()
        result = runner.run("list all tables")
    """
    
    def __init__(self):
        """Initialize the swarm runner."""
        # Ensure agents are registered
        AgentRegistry()
        
        # Build the swarm graph
        self.graph = build_swarm_graph()
        logger.info("Swarm graph built successfully")
    
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
        
        # Initialize state
        initial_state = {
            "user_query": query,
            "user_input": query,
            "conversation_history": [],
        }
        
        # Configure thread for checkpointing
        config = {"configurable": {"thread_id": session_id}}
        
        # Run the graph synchronously using asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            final_state = loop.run_until_complete(
                self.graph.ainvoke(initial_state, config=config)
            )
        finally:
            loop.close()
        
        # Log final state keys and pending actions
        logger.info(f"Final state keys: {list(final_state.keys())}")
        if "pending_human_actions" in final_state:
            logger.info(f"Pending human actions: {len(final_state['pending_human_actions'])}")
        if "approved_actions" in final_state:
            logger.info(f"Approved actions: {len(final_state['approved_actions'])}")
        
        # Process results
        return self._process_result(final_state, session_id)
    
    def _process_result(self, final_state: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """
        Process the final state into a response dict.
        
        Args:
            final_state: Final state from graph execution
            session_id: Session ID for this run
            
        Returns:
            Processed response dict
        """
        coordinator_response = final_state.get("coordinator_response")
        blackboard = final_state.get("blackboard", {})
        findings = final_state.get("findings", [])
        agent_statuses = final_state.get("agent_statuses", {})
        approved_actions = final_state.get("approved_actions", [])
        pending_human_actions = final_state.get("pending_human_actions", [])
        execution_results = final_state.get("action_results")
        
        # If coordinator_response is None but we have findings, generate a summary
        if coordinator_response is None and findings:
            if isinstance(findings, list) and len(findings) > 0:
                summary_parts = []
                entity_names = []  # Collect entity names from discovery findings
                
                for f in findings[:10]:  # Check more findings for entity data
                    if isinstance(f, dict):
                        summary = f.get("summary", "")
                        details = f.get("details", {})
                        # Check if this is a discovery finding with entities
                        if details and isinstance(details, dict):
                            # Try multiple keys: entities, all_table_fqns, sample_tables
                            entities = details.get("entities", [])
                            if not entities:
                                # Fall back to all_table_fqns (strings from catalog_scout)
                                table_fqns = details.get("all_table_fqns", [])
                                if table_fqns and isinstance(table_fqns, list):
                                    entities = [{"fullyQualifiedName": name, "name": name.split(".")[-1]} for name in table_fqns[:50]]
                            if entities and isinstance(entities, list):
                                for entity in entities[:50]:  # Limit to first 50 names
                                    name = entity.get("name") or entity.get("fullyQualifiedName") or "Unknown"
                                    entity_names.append(name)
                        if summary:
                            summary_parts.append(summary)
                    else:
                        summary = getattr(f, 'summary', '')
                        details = getattr(f, 'details', {})
                        # Check if this is a discovery finding with entities
                        if details and isinstance(details, dict):
                            # Try multiple keys: entities, all_table_fqns, sample_tables
                            entities = details.get("entities", [])
                            if not entities:
                                # Fall back to all_table_fqns (strings from catalog_scout)
                                table_fqns = details.get("all_table_fqns", [])
                                if table_fqns and isinstance(table_fqns, list):
                                    entities = [{"fullyQualifiedName": name, "name": name.split(".")[-1]} for name in table_fqns[:50]]
                            if entities and isinstance(entities, list):
                                for entity in entities[:50]:  # Limit to first 50 names
                                    name = entity.get("name") or entity.get("fullyQualifiedName") or "Unknown"
                                    entity_names.append(name)
                        if summary:
                            summary_parts.append(summary)
                
                if summary_parts or entity_names:
                    response_parts = ["I found the following information:"]
                    
                    # Add entity names if we have them
                    if entity_names:
                        # Deduplicate entity names before displaying
                        seen_names = set()
                        unique_names = []
                        for name in entity_names:
                            if name not in seen_names:
                                seen_names.add(name)
                                unique_names.append(name)
                        
                        response_parts.append("\n**Table names:**")
                        for name in unique_names[:30]:  # Show first 30 tables
                            response_parts.append(f"- {name}")
                        if len(unique_names) > 30:
                            response_parts.append(f"- ... and {len(unique_names) - 30} more tables")
                    
                    # Deduplicate summary parts before adding (fixes duplicate hierarchy results)
                    seen_summaries = set()
                    unique_summaries = []
                    for s in summary_parts[:5]:
                        # Use first 100 chars as key to detect duplicates
                        summary_key = s[:100] if s else ""
                        if summary_key and summary_key not in seen_summaries:
                            seen_summaries.add(summary_key)
                            unique_summaries.append(s)
                    
                    # Add unique summary parts
                    for s in unique_summaries:
                        response_parts.append(f"\n{s}")
                    
                    coordinator_response = "\n".join(response_parts)
                    if len(findings) > 10:
                        coordinator_response += f"\n\n...and {len(findings) - 10} more findings."
                else:
                    coordinator_response = f"The swarm completed analysis with {len(findings)} finding(s). Check the findings panel for details."
            else:
                coordinator_response = "The swarm has completed its analysis."
        
        # Build blackboard summary
        blackboard_summary = {
            "findings": findings,
            "findings_count": len(findings),
            "conflicts": blackboard.get("conflicts", []) if isinstance(blackboard, dict) else [],
            "conflicts_count": len(blackboard.get("conflicts", [])) if isinstance(blackboard, dict) else 0,
            "agent_statuses": agent_statuses,
            "execution_phase": blackboard.get("execution_phase", "unknown") if isinstance(blackboard, dict) else "unknown"
        }
        
        return {
            "session_id": session_id,
            "coordinator_response": coordinator_response,
            "blackboard_summary": blackboard_summary,
            "approved_actions": approved_actions,
            "pending_human_actions": pending_human_actions,
            "execution_results": execution_results,
            "final_state": final_state  # Return full state for UI inspection
        }


def get_swarm_runner() -> SwarmRunner:
    """Get a singleton swarm runner instance."""
    if not hasattr(get_swarm_runner, '_instance'):
        get_swarm_runner._instance = SwarmRunner()
    return get_swarm_runner._instance