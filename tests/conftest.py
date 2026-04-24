"""
Pytest configuration and fixtures for OpenMetaMind tests.

All fixtures use real MCP client connections - no mocks.
"""

import pytest
import asyncio
import os
from typing import Dict, Any

from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, HumanMessage
from dotenv import load_dotenv

from src.graph.swarm_graph import build_swarm_graph
from src.agents.registry import AgentRegistry
from src.mcp.client import OpenMetadataMCPClient, get_mcp_client
from src.models.state import SwarmState, AgentFinding, FindingType

# Load environment variables
load_dotenv()


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def real_mcp_client():
    """Create a real MCP client connected to OpenMetadata server."""
    client = get_mcp_client()
    return client


@pytest.fixture
def in_memory_checkpointer():
    """Create an in-memory checkpointer for tests."""
    return MemorySaver()


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
    registry = AgentRegistry()
    yield