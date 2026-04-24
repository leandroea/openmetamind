"""
Complete LangGraph assembly for the OpenMetaMind swarm.

This module assembles all the previously built nodes into a complete StateGraph
with proper edges and routing logic.
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send, Command
import os

from ..models.state import SwarmState
from .nodes import coordinator, planner, dispatcher, agent_executor_node, integrity_critic, action_executor_node
from .dispatcher import dispatcher_conditional_edge


def build_swarm_graph(checkpointer=None):
    """
    Build the complete OpenMetaMind swarm LangGraph.

    Args:
        checkpointer: Optional checkpointer for state persistence.
            If None, uses MemorySaver (in-memory checkpointing).

    Returns:
        Compiled StateGraph ready for execution
    """
    if checkpointer is None:
        checkpointer = MemorySaver()
    
    # Create the graph
    workflow = StateGraph(SwarmState)
    
    # Add all nodes
    workflow.add_node("coordinator", coordinator)
    workflow.add_node("planner", planner)
    workflow.add_node("dispatcher", dispatcher)
    workflow.add_node("agent_executor", agent_executor_node)
    workflow.add_node("integrity_critic", integrity_critic)
    workflow.add_node("action_executor", action_executor_node)
    
    # Set entry point
    workflow.set_entry_point("coordinator")
    
    # Add edges
    # Coordinator routes to planner (if delegating) or END (if answering/clarifying)
    workflow.add_conditional_edges(
        "coordinator",
        lambda state: state.get("next", "planner"),
        {
            "planner": "planner",
            "end": END
        }
    )
    
    # Planner always goes to dispatcher
    workflow.add_edge("planner", "dispatcher")
    
    # Dispatcher routes based on whether it has Send objects to spawn
    # The conditional edge function checks state and returns either Send objects or a node name
    workflow.add_conditional_edges(
        "dispatcher",
        dispatcher_conditional_edge,
        {
            "agent_executor": "agent_executor",  # Send API will trigger agent_executor in parallel
            "integrity_critic": "integrity_critic"  # No pending tasks, go to critic
        }
    )
    
    # Agent executor routes based on completion status
    workflow.add_conditional_edges(
        "agent_executor",
        lambda state: _should_go_to_dispatcher(state),
        {
            "dispatcher": "dispatcher",  # Go back to dispatcher to check for more tasks
            "integrity_critic": "integrity_critic"  # No more tasks, go to critic
        }
    )
    
    # Integrity critic routes based on its decision
    workflow.add_conditional_edges(
        "integrity_critic",
        lambda state: state.get("next", "human_gate"),
        {
            "action_executor": "action_executor",
            "planner": "planner",  # For retry (REJECT_AND_RETRY)
            "human_gate": END      # For now, end at human gate (would connect to UI)
        }
    )
    
    # Action executor always ends the workflow (results go to human gate for approval)
    workflow.add_edge("action_executor", END)
    
    # Compile the workflow
    return workflow.compile(checkpointer=checkpointer)


def _should_go_to_dispatcher(state: SwarmState) -> Literal["dispatcher", "integrity_critic"]:
    """
    Determine if there are more pending tasks and we should go back to dispatcher.
    
    Args:
        state: Current swarm state
        
    Returns:
        "dispatcher" if there are more pending tasks, "integrity_critic" otherwise
    """
    from ..models.plan import ExecutionPlan
    
    execution_plan = state.get("execution_plan")
    completed_subtasks = set(state.get("completed_subtasks", []))
    
    if not execution_plan:
        # No plan, go to critic
        return "integrity_critic"
    
    # Convert dict to ExecutionPlan if needed
    if isinstance(execution_plan, dict):
        plan = ExecutionPlan(**execution_plan)
    else:
        plan = execution_plan
    
    # Check if any subtasks are still pending
    for subtask in plan.subtasks:
        if subtask.subtask_id not in completed_subtasks:
            # Check if all dependencies are satisfied
            if all(dep in completed_subtasks for dep in subtask.dependencies):
                # Found a pending task, go back to dispatcher
                return "dispatcher"
    
    # No pending tasks, go to critic
    return "integrity_critic"


def _should_go_to_critic(state: SwarmState) -> Literal["integrity_critic", "agent_executor"]:
    """
    Determine if all planned subtasks are completed and we should go to the critic.
    
    Args:
        state: Current swarm state
        
    Returns:
        "integrity_critic" if all subtasks are done, "agent_executor" otherwise
    """
    execution_plan = state.get("execution_plan")
    completed_subtasks = set(state.get("completed_subtasks", []))
    
    if not execution_plan:
        # No plan, go to critic
        return "integrity_critic"
    
    # Get all subtask IDs from the plan
    if isinstance(execution_plan, dict):
        subtasks = execution_plan.get("subtasks", [])
        all_subtask_ids = {st.get("subtask_id") for st in subtasks if st.get("subtask_id")}
    else:
        # Assuming it's an ExecutionPlan object
        all_subtask_ids = {st.subtask_id for st in execution_plan.subtasks}
    
    # If all subtasks are completed, go to critic
    if all_subtask_ids and all_subtask_ids.issubset(completed_subtasks):
        return "integrity_critic"
    
    # Otherwise, continue executing agents
    return "agent_executor"


# Convenience function to get a swarm graph instance
def get_swarm_graph():
    """Get a compiled OpenMetaMind swarm graph."""
    return build_swarm_graph()


if __name__ == "__main__":
    # For testing the graph structure
    graph = get_swarm_graph()
    print("OpenMetaMind swarm graph created successfully")
    print(f"Graph nodes: {list(graph.nodes.keys())}")