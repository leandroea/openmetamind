"""
Pytest configuration and fixtures for OpenMetaMind tests.

All fixtures use real MCP client connections - no mocks.
"""

import pytest
import asyncio
import os

from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

from src.agents.registry import AgentRegistry
from src.mcp.client import get_mcp_client

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


@pytest.fixture(autouse=True)
def reset_agent_registry():
    """Reset the agent registry before each test."""
    registry = AgentRegistry()
    yield