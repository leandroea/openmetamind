"""Test coordinator with real LLM connections."""
import pytest
import os
from src.graph.coordinator import Coordinator
from src.models.state import SwarmState


@pytest.fixture
def coordinator():
    """Create a real coordinator instance with MiniMax LLM."""
    return Coordinator()


@pytest.fixture
def swarm_state():
    """Create a real SwarmState instance."""
    return SwarmState(
        user_input="Show me all tables in the customers database",
        conversation_history=[],
        current_plan=None,
        active_agents=[],
        findings=[],
        pending_tasks=[],
        next="coordinator"
    )


@pytest.mark.asyncio
async def test_coordinator_initialization(coordinator):
    """Test coordinator can be initialized with MiniMax LLM."""
    assert coordinator is not None
    assert coordinator.llm is not None
    assert hasattr(coordinator, 'intent_chain')
    assert hasattr(coordinator, 'answer_chain')
    assert hasattr(coordinator, 'clarify_chain')


@pytest.mark.asyncio 
async def test_coordinator_chat_interaction(coordinator, swarm_state):
    """Test coordinator with real MiniMax LLM call."""
    result = coordinator(swarm_state)
    
    # Verify result structure
    assert isinstance(result, dict)
    assert "conversation_history" in result
    assert "next" in result
    
    # Should delegate to planner since query references OpenMetadata entities
    assert result["next"] in ["planner", "end"]
    
    print(f"Result: {result}")


@pytest.mark.asyncio
async def test_coordinator_direct_answer(coordinator):
    """Test coordinator for simple direct answer intent."""
    state = SwarmState(
        user_input="What is 2+2?",
        conversation_history=[],
        current_plan=None,
        active_agents=[],
        findings=[],
        pending_tasks=[],
        next="coordinator"
    )
    
    result = coordinator(state)
    
    # Should either answer directly or delegate
    assert "next" in result
    assert result["next"] in ["planner", "end"]
    print(f"Direct answer result: {result}")


@pytest.mark.asyncio
async def test_coordinator_with_history(coordinator):
    """Test coordinator with conversation history."""
    from langchain_core.messages import HumanMessage, AIMessage
    
    state = SwarmState(
        user_input="What about the orders table?",
        conversation_history=[
            HumanMessage(content="Show me the customers table"),
            AIMessage(content="The customers table has 1000 rows and includes columns: id, name, email")
        ],
        current_plan=None,
        active_agents=[],
        findings=[],
        pending_tasks=[],
        next="coordinator"
    )
    
    result = coordinator(state)
    
    assert "next" in result
    print(f"History result: {result}")