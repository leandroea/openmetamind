"""
Complete LangGraph assembly for the OpenMetaMind swarm.

This module assembles all the previously built nodes into a complete StateGraph
with proper edges and routing logic using the Supervisor/Manager pattern.

Architecture:
    Coordinator → Planner → Dispatcher → Supervisor → IntegrityCritic → ActionExecutor
                                      ↑
                                      └── (loops back while tasks remain)
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os

from ..models.state import SwarmState
from .nodes import coordinator, planner, dispatcher, supervisor, integrity_critic, action_executor_node


def build_swarm_graph(checkpointer=None):
    """
    Build the complete OpenMetaMind swarm LangGraph.

    Uses the Supervisor/Manager pattern for sequential agent execution
    instead of parallel execution via Send API.

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
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("integrity_critic", integrity_critic)
    workflow.add_node("action_executor", action_executor_node)
    
    # Set entry point
    workflow.set_entry_point("coordinator")
    
    # Add edges - Linear flow with Supervisor loop
    
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
    
    # Dispatcher initializes task queue and routes to supervisor
    workflow.add_edge("dispatcher", "supervisor")
    
    # Supervisor loops back to itself while there are pending tasks,
    # or routes to integrity_critic when done
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state.get("next", "integrity_critic"),
        {
            "supervisor": "supervisor",  # Loop back for next task
            "integrity_critic": "integrity_critic"  # All tasks done
        }
    )
    
    # Integrity critic routes based on its decision
    workflow.add_conditional_edges(
        "integrity_critic",
        lambda state: state.get("next", "human_gate"),
        {
            "action_executor": "action_executor",
            "planner": "planner",  # For retry (REJECT_AND_RETRY)
            "human_gate": END      # End at human gate (would connect to UI)
        }
    )
    
    # Action executor always ends the workflow (results go to human gate for approval)
    workflow.add_edge("action_executor", END)
    
    # Compile the workflow
    return workflow.compile(checkpointer=checkpointer)


# Convenience function to get a swarm graph instance
def get_swarm_graph():
    """Get a compiled OpenMetaMind swarm graph."""
    return build_swarm_graph()


if __name__ == "__main__":
    # For testing the graph structure
    graph = get_swarm_graph()
    print("OpenMetaMind swarm graph created successfully")
    print(f"Graph nodes: {list(graph.nodes.keys())}")