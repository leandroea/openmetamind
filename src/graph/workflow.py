"""
LangGraph workflow for OpenMetaMind swarm.

This module defines the complete workflow graph connecting all nodes:
Coordinator -> Planner -> Dispatcher -> [Agent Executors (parallel)] -> Integrity Critic -> [Action Executor | Human Gate]
"""

from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import SwarmState
from .coordinator import Coordinator
from .planner import Planner
from .dispatcher import Dispatcher
from .agent_executor import agent_executor_node
from .integrity_critic import IntegrityCritic
from .action_executor import action_executor_node, action_executor_dry_run_node


def create_openmetamind_workflow(checkpointer=None):
    """
    Create the OpenMetaMind LangGraph workflow.
    
    Args:
        checkpointer: Optional checkpointer for state persistence (defaults to MemorySaver)
        
    Returns:
        Compiled LangGraph workflow
    """
    if checkpointer is None:
        checkpointer = MemorySaver()
    
    # Initialize nodes
    coordinator = Coordinator()
    planner = Planner()
    dispatcher = Dispatcher()
    agent_executor = agent_executor_node  # This is already a function
    integrity_critic = IntegrityCritic()
    action_executor = action_executor_node
    
    # Create the graph
    workflow = StateGraph(SwarmState)
    
    # Add nodes
    workflow.add_node("coordinator", coordinator)
    workflow.add_node("planner", planner)
    workflow.add_node("dispatcher", dispatcher)
    workflow.add_node("agent_executor", agent_executor)
    workflow.add_node("integrity_critic", integrity_critic)
    workflow.add_node("action_executor", action_executor)
    # Human gate would be implemented separately (Streamlit/Slack UI)
    
    # Set entry point
    workflow.set_entry_point("coordinator")
    
    # Add edges
    workflow.add_conditional_edges(
        "coordinator",
        lambda state: state.get("next", "planner"),
        {
            "planner": "planner",
            "end": END
        }
    )
    
    workflow.add_conditional_edges(
        "planner",
        lambda state: "dispatcher",
        {
            "dispatcher": "dispatcher"
        }
    )
    
    # Dispatcher uses Send API for parallel execution - no conditional edge needed
    # The dispatcher returns a list of Send objects that LangGraph executes automatically
    workflow.add_edge("dispatcher", "agent_executor")
    
    workflow.add_conditional_edges(
        "agent_executor",
        lambda state: state.get("next", "integrity_critic"),
        {
            "integrity_critic": "integrity_critic",
            "agent_executor": "agent_executor"  # For looping if needed
        }
    )
    
    workflow.add_conditional_edges(
        "integrity_critic",
        lambda state: state.get("next", "human_gate"),
        {
            "action_executor": "action_executor",
            "planner": "planner",  # For retry
            "human_gate": "human_gate"  # Would connect to UI
        }
    )
    
    workflow.add_conditional_edges(
        "action_executor",
        lambda state: "human_gate",  # After action execution, go to human gate for approval/notification
        {
            "human_gate": "human_gate"
        }
    )
    
    # Human gate would normally wait for user input, then either:
    # - End the workflow (if actions are rejected)
    # - Go to action_executor for execution (if approved)
    # For now, we'll simplify and end after human gate
    workflow.add_conditional_edges(
        "human_gate",
        lambda state: "end",  # In a real implementation, this would check user approval
        {
            "end": END,
            "action_executor": "action_executor"  # If approved
        }
    )
    
    # Compile the workflow
    return workflow.compile(checkpointer=checkpointer)


# Convenience function to get a workflow instance
def get_workflow():
    """Get a compiled OpenMetaMind workflow."""
    return create_openmetamind_workflow()


if __name__ == "__main__":
    # For testing the workflow structure
    workflow = get_workflow()
    print("OpenMetaMind workflow created successfully")
    print(f"Workflow nodes: {list(workflow.nodes.keys())}")