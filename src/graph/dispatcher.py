"""
Dispatcher node for the OpenMetaMind swarm.

Executes the plan using LangGraph's Send API. Handles parallelization, retries, and timeouts.
"""

import logging
from typing import List, Dict, Any
from langgraph.types import Send, Command

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

    def __call__(self, state: SwarmState) -> Command:
        """
        Execute the Dispatcher node - returns Command with Send objects for parallel execution.

        Args:
            state: Current swarm state containing execution_plan

        Returns:
            Command containing list of Send objects to execute agent_executor nodes in parallel,
            or routing to integrity_critic if no pending tasks
        """
        plan_dict = state.get("execution_plan")
        if not plan_dict:
            # No plan to execute - go directly to integrity_critic
            return Command(goto="integrity_critic")

        # Convert dict to ExecutionPlan if needed
        if isinstance(plan_dict, dict):
            from ..models.plan import ExecutionPlan
            plan = ExecutionPlan(**plan_dict)
        else:
            plan = plan_dict

        # Get completed subtasks from state
        completed_subtasks = set(state.get("completed_subtasks", []))

        # Determine which subtasks are ready to execute (dependencies satisfied and not yet completed)
        sends = []

        # Check all subtasks in the plan
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
            # Return Command with Send objects for parallel execution
            return Command(goto=sends)
        else:
            # No pending tasks, go to integrity_critic
            return Command(goto="integrity_critic")


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