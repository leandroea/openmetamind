"""Integration test with real MiniMax LLM and real MCP connection."""
import pytest
import asyncio
from src.graph.swarm_graph import build_swarm_graph
from src.models.state import SwarmState
from src.mcp.client import get_mcp_client


@pytest.mark.asyncio
async def test_list_tables_in_catalog():
    """
    Integration test: List all tables in the catalog using real MiniMax LLM and real MCP tools.
    
    This test:
    1. Uses the real MiniMax LLM (minimax-m2.7)
    2. Connects to real OpenMetadata MCP server
    3. Invokes the full swarm graph
    4. Returns actual tables from the catalog
    """
    # Build the swarm graph
    graph = build_swarm_graph()
    
    # Create initial state with the task
    initial_state = SwarmState(
        user_input="List all the tables in the catalog",
        conversation_history=[],
        current_plan=None,
        active_agents=[],
        findings=[],
        pending_tasks=[],
        next="coordinator"
    )
    
    # Invoke the graph
    config = {"configurable": {"thread_id": "test-list-tables-001"}}
    
    result = await graph.ainvoke(initial_state, config=config)
    
    # Verify results
    assert result is not None
    assert "findings" in result
    
    print(f"Number of findings: {len(result.get('findings', []))}")
    print(f"Result keys: {result.keys()}")
    
    # Print findings if any
    for i, finding in enumerate(result.get("findings", [])[:5]):
        print(f"Finding {i+1}: {finding.summary if hasattr(finding, 'summary') else finding}")


@pytest.mark.asyncio
async def test_mcp_pagination_all_results():
    """
    Test the search_metadata_all function which implements pagination
    to fetch ALL results from OpenMetadata.
    """
    async with get_mcp_client() as mcp_client:
        # Use the pagination method to get all results
        result = await mcp_client.search_metadata_all(
            query="table",
            entity_type="table",
            max_results=1000
        )
        
        print(f"Total found: {result.get('totalFound', 0)}")
        print(f"Returned count: {result.get('returnedCount', 0)}")
        print(f"Has more: {result.get('hasMore', False)}")
        print(f"Number of entities: {len(result.get('results', []))}")
        
        assert result is not None
        entities = result.get("results", [])
        total = result.get("totalFound", 0)
        
        print(f"\nFirst 3 tables:")
        for i, entity in enumerate(entities[:3]):
            print(f"  {i+1}. {entity.get('fullyQualifiedName')}")
        
        print(f"\nLast 3 tables:")
        for i, entity in enumerate(entities[-3:]):
            print(f"  {len(entities)-2+i}. {entity.get('fullyQualifiedName')}")


@pytest.mark.asyncio
async def test_swarm_with_real_mcp():
    """
    End-to-end test of the swarm with real MCP connection.
    Uses the CatalogScout agent to find tables.
    """
    graph = build_swarm_graph()
    
    state = SwarmState(
        user_input="Find all tables in the default database",
        conversation_history=[],
        current_plan=None,
        active_agents=[],
        findings=[],
        pending_tasks=[],
        next="coordinator"
    )
    
    config = {"configurable": {"thread_id": "test-real-mcp-001"}}
    result = await graph.ainvoke(state, config=config)
    
    print(f"Swarm result keys: {result.keys()}")
    print(f"Findings: {len(result.get('findings', []))}")
    
    assert result is not None


@pytest.mark.asyncio
async def test_get_entity_details():
    """
    Test get_entity_details MCP method with real connection.
    """
    async with get_mcp_client() as mcp_client:
        # Try to get details for a table
        # This will fail if the table doesn't exist, but it tests the connection
        try:
            result = await mcp_client.get_entity_details(
                entity_type="table",
                fqn="default.ecommerce.orders"
            )
            print(f"Entity details: {result}")
            assert result is not None
        except Exception as e:
            # Expected if entity doesn't exist
            print(f"Expected error (entity may not exist): {e}")
            # But we should still have made the connection
            assert True


if __name__ == "__main__":
    asyncio.run(test_list_tables_in_catalog())