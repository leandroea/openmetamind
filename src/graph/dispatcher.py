"""
Dispatcher node for the OpenMetaMind swarm.

The Dispatcher initializes the task queue from the Planner's execution plan.
Instead of using LangGraph's Send API for parallel execution, the Dispatcher
sets up sequential task execution via the Supervisor.

Supervisor Pattern:
- Dispatcher initializes the task queue
- Supervisor iterates through tasks sequentially
- Each task completion triggers the next Supervisor iteration
"""

import logging
from typing import List, Dict, Any

from ..models.state import SwarmState
from ..models.plan import ExecutionPlan, Subtask

logger = logging.getLogger(__name__)


class Dispatcher:
    """
    The Dispatcher node in the LangGraph workflow.

    Responsibilities:
    - Initialize task queue from execution plan
    - Prepare tasks for sequential execution by Supervisor
    - Handle empty plans gracefully
    """

    def __init__(self):
        """Initialize the Dispatcher."""
        pass

    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute the Dispatcher node.
        
        Initializes the pending_tasks queue from the execution plan
        and routes to the Supervisor for sequential execution.

        Args:
            state: Current swarm state containing execution_plan

        Returns:
            Dict with pending_tasks queue and routing decision
        """
        plan_dict = state.get("execution_plan")
        
        if not plan_dict:
            logger.info("Dispatcher: No execution plan found, skipping to integrity_critic")
            return {"next": "integrity_critic"}
        
        # Convert dict to ExecutionPlan if needed
        if isinstance(plan_dict, dict):
            plan = ExecutionPlan(**plan_dict)
        else:
            plan = plan_dict
        
        # Convert subtasks to pending task queue
        pending_tasks = []
        for subtask in plan.subtasks:
            task_dict = {
                "subtask_id": subtask.subtask_id,
                "agent_id": subtask.agent_id,
                "task": subtask.task_description,
                "required_inputs": subtask.required_inputs,
                "dependencies": subtask.dependencies,
                "produces_output": subtask.produces_output,
            }
            pending_tasks.append(task_dict)
        
        if not pending_tasks:
            logger.info("Dispatcher: Execution plan has no subtasks, skipping to integrity_critic")
            return {"next": "integrity_critic"}
        
        logger.info(f"Dispatcher: Initialized {len(pending_tasks)} tasks for sequential execution")
        
        # Initialize the task queue and route to supervisor
        return {
            "pending_tasks": pending_tasks,
            "current_task_index": 0,
            "next": "supervisor"
        }


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
