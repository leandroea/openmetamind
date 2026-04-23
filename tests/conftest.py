"""
Pytest configuration and fixtures for OpenMetaMind tests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, HumanMessage

from src.graph.swarm_graph import build_swarm_graph
from src.agents.registry import AgentRegistry
from src.mcp.client import OpenMetadataMCPClient
from src.models.state import SwarmState, AgentFinding, FindingType


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_mcp_client():
    """Create a mocked MCP client for unit tests."""
    mock_client = AsyncMock(spec=OpenMetadataMCPClient)
    
    # Mock list_entities
    mock_client.list_entities = AsyncMock(return_value=[])
    
    # Mock get_table_profile
    mock_client.get_table_profile = AsyncMock(return_value=MagicMock(
        tableName="test_table",
        databaseName="test_db",
        columnCount=5,
        rowCount=1000
    ))
    
    # Mock get_column_profile
    mock_client.get_column_profile = AsyncMock(return_value=MagicMock(
        columnName="test_column",
        dataType="varchar"
    ))
    
    # Mock get_usage_stats
    mock_client.get_usage_stats = AsyncMock(return_value=MagicMock(
        entityFQN="test_db.test_table",
        totalQueries=100,
        uniqueUsers=10
    ))
    
    # Mock write operations
    mock_client.add_tags = AsyncMock(return_value=True)
    mock_client.update_owner = AsyncMock(return_value=True)
    mock_client.update_description = AsyncMock(return_value=True)
    
    return mock_client


@pytest.fixture
def in_memory_checkpointer():
    """Create an in-memory checkpointer for tests."""
    return MemorySaver()


@pytest.fixture
def mock_llm():
    """Create a mocked LLM for deterministic tests."""
    mock = MagicMock()
    # Default: return delegate_lightweight intent for coordinator tests
    delegate_response = MagicMock()
    delegate_response.content = '{"intent": "delegate_lightweight", "reasoning": "Test delegation"}'
    mock.invoke = MagicMock(return_value=delegate_response)
    mock.ainvoke = AsyncMock(return_value=delegate_response)
    # Also support the chain pattern (prompt | llm | parser)
    # When used in a pipe chain, the mock needs to support the | operator
    mock.__or__ = lambda self, other: MagicMock(invoke=MagicMock(return_value={"intent": "delegate_lightweight", "reasoning": "Test delegation"}))
    return mock


@pytest.fixture
def built_graph(in_memory_checkpointer, mock_llm):
    """Build a swarm graph with mocked LLM for testing."""
    with patch('src.graph.coordinator.ChatOpenAI', return_value=mock_llm), \
         patch('src.graph.planner.ChatOpenAI', return_value=mock_llm), \
         patch('src.graph.integrity_critic.ChatOpenAI', return_value=mock_llm):
        graph = build_swarm_graph(checkpointer=in_memory_checkpointer)
        return graph


@pytest.fixture
def sample_agent_finding() -> AgentFinding:
    """Create a sample agent finding for testing."""
    return AgentFinding(
        agent_id="test_agent",
        subtask_id="test_subtask",
        task_description="Test task",
        finding_type=FindingType.CLASSIFICATION,
        target_entity="test_db.test_table",
        summary="Test finding summary",
        details={"test": "data"},
        confidence=0.85,
        proposed_actions=[],
        mcp_tool_calls=[],
        llm_reasoning="Test reasoning"
    )


@pytest.fixture
def sample_swarm_state() -> SwarmState:
    """Create a sample swarm state for testing."""
    return {
        "user_query": "List tables in customers database",
        "user_input": "List tables in customers database",
        "conversation_history": [],
        "blackboard": {
            "findings": [],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "planning"
        },
        "execution_plan": None,
        "completed_subtasks": [],
        "current_parallel_group": [],
        "coordinator_notes": None,
        "delegated_task": None,
        "coordinator_response": None,
        "critic_review": None,
        "approved_actions": [],
        "execution_results": None,
        "executed_actions": []
    }


@pytest.fixture(autouse=True)
def reset_agent_registry():
    """Reset the agent registry before each test."""
    # Clear the registry before each test
    registry = AgentRegistry()
    # Note: In a real scenario, we'd need to reset the singleton
    # For now, tests should import fresh agents
    yield
    # Cleanup after test if needed


@pytest.fixture
def mock_openmetadata_response():
    """Create mock OpenMetadata API responses."""
    return {
        "entities": [
            {
                "id": "entity-1",
                "name": "users",
                "fullyQualifiedName": "customers.users",
                "description": "User accounts table"
            },
            {
                "id": "entity-2",
                "name": "orders",
                "fullyQualifiedName": "customers.orders",
                "description": "Orders table"
            }
        ]
    }