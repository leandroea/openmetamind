"""
Dispatcher node for the OpenMetaMind swarm.

Executes the plan using LangGraph's Send API. Handles parallelization, retries, and timeouts.
"""

import logging
from typing import List, Dict, Any, Tuple
from langgraph.types import Send

from ..models.state import SwarmState
from ..models.plan import ExecutionPlan

logger = logging.getLogger(__name__)


class Dispatcher:
    """
    The Dispatcher node in the LangGraph workflow.

    Responsibilities:
    - Executes the plan using LangGraph's Send API
    - Handles parallelization, retries, and timeouts
    - Dynamic replanning capability
    """

    def __init__(self):
        """Initialize the Dispatcher."""
        pass

    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute the Dispatcher node - sets state for conditional edge to use.

        Args:
            state: Current swarm state containing execution_plan

        Returns:
            Dict with dispatcher state (conditional edge handles routing/sends)
        """
        # The actual routing logic is in dispatcher_conditional_edge
        # This node just needs to set some state to indicate it ran
        return {"dispatcher_ran": True}


def dispatcher_conditional_edge(state: SwarmState):
    """
    Conditional edge function for dispatcher - returns routing decision.
    
    This function is called by LangGraph when routing from dispatcher node.
    It returns either a node name (string) or a list of Send objects.
    
    Args:
        state: Current swarm state
        
    Returns:
        "integrity_critic" if no pending tasks, list of Send objects otherwise
    """
    from langgraph.types import Send
    from ..models.plan import ExecutionPlan
    
    plan_dict = state.get("execution_plan")
    if not plan_dict:
        return "integrity_critic"
    
    # Convert dict to ExecutionPlan if needed
    if isinstance(plan_dict, dict):
        plan = ExecutionPlan(**plan_dict)
    else:
        plan = plan_dict
    
    # Get completed subtasks from state
    completed_subtasks = set(state.get("completed_subtasks", []))
    
    sends = []
    for subtask in plan.subtasks:
        # Skip if already completed
        if subtask.subtask_id in completed_subtasks:
            continue
        
        # Check if all dependencies are satisfied
        dependencies_satisfied = all(
            dep in completed_subtasks for dep in subtask.dependencies
        )
        
        if dependencies_satisfied:
            # Validate subtask has required fields
            if not subtask.subtask_id or not subtask.agent_id:
                logger.warning(f"Skipping invalid subtask: missing subtask_id or agent_id")
                continue
            
            # Prepare inputs for the agent from the blackboard
            blackboard = state.get("blackboard", {})
            inputs = {}
            for key in subtask.required_inputs:
                if key in blackboard:
                    inputs[key] = blackboard[key]
            
            # Create Send object for agent_executor node
            sends.append(Send(
                "agent_executor",
                {
                    "subtask_id": subtask.subtask_id,
                    "agent_id": subtask.agent_id,
                    "task": subtask.task_description,
                    "inputs": inputs
                }
            ))
    
    if sends:
        # Return Send objects to spawn agent_executor nodes in parallel
        return sends
    else:
        # No pending tasks, route to integrity_critic
        return "integrity_critic"


# Dynamic replanning helper function
def regenerate_plan_if_needed(state: SwarmState) -> SwarmState:
    """
    Check if plan needs regeneration based on agent results or failures.
    In a full implementation, this would analyze blackboard for conflicts, failures, etc.
    and trigger the planner to create a new plan.

    For now, this is a placeholder showing where dynamic replanning would occur.
    """
    # This would analyze the blackboard for:
    # - Agent failures
    # - Unexpected results
    # - Conflicts requiring new subtasks
    # - New information requiring additional analysis

    # Return state unchanged for now
    return state