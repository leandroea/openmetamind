"""Real integration tests for CatalogScout agent using actual LLM and MCP connections."""

import pytest
import logging
import sys
from src.agents.catalog_scout import CatalogScout

# Enable UTF-8 output on Windows
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'

logger = logging.getLogger(__name__)


def safe_print(msg):
    """Print with proper encoding for Windows."""
    try:
        print(msg)
    except UnicodeEncodeError:
        clean = msg.encode('ascii', errors='replace').decode('ascii')
        print(clean)


@pytest.mark.asyncio
async def test_list_tables():
    """Test 1: List all tables in the catalog."""
    print("\n" + "="*60)
    print("TEST 1: List Tables")
    print("="*60)
    
    agent = CatalogScout()
    result = await agent.execute(
        task="List all available tables from OpenMetadata",
        inputs={},
        mcp_client=None
    )
    safe_print(f"RESULT: {result[:500]}..." if len(result) > 500 else f"RESULT: {result}")
    return result


@pytest.mark.asyncio
async def test_search_entities():
    """Test 2: Search for entities matching a query."""
    print("\n" + "="*60)
    print("TEST 2: Search Entities")
    print("="*60)
    
    agent = CatalogScout()
    result = await agent.execute(
        task="Search for any table or database related to 'shop' or 'store'",
        inputs={},
        mcp_client=None
    )
    safe_print(f"RESULT: {result[:500]}..." if len(result) > 500 else f"RESULT: {result}")
    return result


@pytest.mark.asyncio
async def test_get_entity_details():
    """Test 3: Get details of a specific entity."""
    print("\n" + "="*60)
    print("TEST 3: Get Entity Details")
    print("="*60)
    
    agent = CatalogScout()
    result = await agent.execute(
        task="Get details about any database or table you can find in the catalog. List the first database you discover.",
        inputs={},
        mcp_client=None
    )
    safe_print(f"RESULT: {result[:500]}..." if len(result) > 500 else f"RESULT: {result}")
    return result


@pytest.mark.asyncio
async def test_discover_hierarchy():
    """Test 4: Discover the catalog hierarchy."""
    print("\n" + "="*60)
    print("TEST 4: Discover Hierarchy")
    print("="*60)
    
    agent = CatalogScout()
    result = await agent.execute(
        task="Build a hierarchy view showing databases, schemas and tables structure. What databases are available and what tables do they contain?",
        inputs={},
        mcp_client=None
    )
    safe_print(f"RESULT: {result[:500]}..." if len(result) > 500 else f"RESULT: {result}")
    return result


@pytest.mark.asyncio
async def test_explore_catalog():
    """Test 5: Explore catalog with multiple entity types."""
    print("\n" + "="*60)
    print("TEST 5: Explore Multiple Entity Types")
    print("="*60)
    
    agent = CatalogScout()
    result = await agent.execute(
        task="Explore the catalog and tell me what types of entities are available (tables, databases, dashboards, pipelines, etc). Give me an overview of what's in OpenMetadata.",
        inputs={},
        mcp_client=None
    )
    safe_print(f"RESULT: {result[:500]}..." if len(result) > 500 else f"RESULT: {result}")
    return result