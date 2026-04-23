"""
Agent Executor node for the OpenMetaMind swarm.

Executes individual subtasks using the appropriate agent.
"""

import asyncio
import logging
from typing import Dict, Any

from ..models.state import SwarmState, AgentFinding
from ..models.plan import Subtask
from ..agents.registry import AgentRegistry
from ..mcp.client import get_mcp_client

logger = logging.getLogger(__name__)


class AgentExecutor:
    """
    The Agent Executor node in the LangGraph workflow.
    
    Responsibilities:
    - Execute a single subtask using the appropriate agent
    - Handle agent execution lifecycle
    - Return findings to be added to the blackboard
    """

    def __init__(self):
        """Initialize the Agent Executor."""
        pass

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Agent Executor node.
        
        Args:
            state: Dictionary containing:
                - subtask_id: ID of the subtask to execute
                - agent_id: ID of the agent to use
                - task: Task description for the agent
                - inputs: Input data from blackboard
                
        Returns:
            Dictionary with updates to add to the state
        """
        subtask_id = state.get("subtask_id")
        agent_id = state.get("agent_id")
        task = state.get("task", "")
        inputs = state.get("inputs", {})
        
        logger.info(f"Agent Executor starting: agent={agent_id}, subtask={subtask_id}")
        
        # Get the agent from registry
        registry = AgentRegistry()
        agent = registry.get_agent(agent_id)
        
        if not agent:
            error_msg = f"Agent {agent_id} not found in registry"
            logger.error(error_msg)
            # Return an error finding
            from ..models.state import AgentFinding
            error_finding = AgentFinding(
                agent_id=agent_id or "unknown",
                subtask_id=subtask_id or "unknown",
                task_description=task,
                finding_type="other",
                summary=error_msg,
                details={"error": error_msg},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning="Agent not found in registry"
            )
            return {
                "findings": [error_finding.dict() if hasattr(error_finding, 'dict') else error_finding],
                "agent_statuses": {agent_id: "failed"} if agent_id else {},
                "completed_subtasks": [subtask_id] if subtask_id else []  # Mark as completed even if failed
            }
        
        # Get MCP client
        mcp_client = get_mcp_client()
        
        try:
            # Execute the agent
            async with mcp_client as client:
                finding = await agent.execute(task=task, inputs=inputs, mcp_client=client)
                
                logger.info(f"Agent Executor completed: agent={agent_id}, confidence={finding.confidence}")
                
                # Return the finding to be added to blackboard and mark agent as completed
                return {
                    "findings": [finding.dict() if hasattr(finding, 'dict') else finding],
                    "agent_statuses": {agent_id: "completed"},
                    "completed_subtasks": [subtask_id]  # Mark this subtask as completed
                }
                
        except Exception as e:
            logger.error(f"Agent Executor failed: agent={agent_id}, error={str(e)}", exc_info=True)
            # Return an error finding
            from ..models.state import AgentFinding
            error_finding = AgentFinding(
                agent_id=agent_id,
                subtask_id=subtask_id,
                task_description=task,
                finding_type="other",
                summary=f"Agent execution failed: {str(e)}",
                details={"error": str(e), "agent_id": agent_id},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"Agent {agent_id} failed during execution: {str(e)}"
            )
            return {
                "findings": [error_finding.dict() if hasattr(error_finding, 'dict') else error_finding],
                "agent_statuses": {agent_id: "failed"},
                "completed_subtasks": [subtask_id]  # Mark as completed even if failed
            }


# Synchronous wrapper for LangGraph (which expects sync functions)
def agent_executor_node(state: SwarmState) -> Dict[str, Any]:
    """
    Synchronous wrapper for the AgentExecutor async class.
    
    LangGraph expects synchronous nodes, so we run the async executor in an event loop.
    The Send API passes the payload as the state to this function.
    """
    # Create a new event loop for this execution
    # In a production setting, you might want to reuse loops or use async nodes
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # The state passed to this function contains the agent execution parameters
        # from the Send API: subtask_id, agent_id, task, inputs
        result = loop.run_until_complete(
            AgentExecutor()(
                {
                    "subtask_id": state.get("subtask_id"),
                    "agent_id": state.get("agent_id"),
                    "task": state.get("task", ""),
                    "inputs": state.get("inputs", {})
                }
            )
        )
        return result
    finally:
        loop.close()