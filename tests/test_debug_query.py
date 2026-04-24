"""Debug test for catalog scout query building."""
import pytest
from src.agents.catalog_scout import CatalogScout

scout = CatalogScout()

def test_query_building():
    """Test _build_search_query with various inputs."""
    test_cases = [
        # (input, expected_query)
        ("list all the tables in the catalog", "table"),
        ("list all tables", "table"),
        ("show tables", "table"),
        ("List all the tables in the catalog", "table"),  # Capital L
        ("LIST ALL THE TABLES IN THE CATALOG", "table"),  # All caps
    ]
    
    print("\nTesting _build_search_query:")
    for task, expected in test_cases:
        query = scout._build_search_query(task)
        print(f"  Task: '{task}' -> Query: '{query}' (expected: '{expected}')")
        assert query == expected, f"Expected '{expected}' but got '{query}'"


@pytest.mark.asyncio
async def test_catalog_scout_execute():
    """Test CatalogScout.execute with real MCP connection."""
    from src.mcp.client import get_mcp_client
    
    async with get_mcp_client() as mcp_client:
        finding = await scout.execute(
            task="list all the tables in the catalog",
            inputs={},
            mcp_client=mcp_client
        )
        
        print(f"\nCatalog Scout Result:")
        print(f"  Summary: {finding.summary}")
        print(f"  Total count in details: {finding.details.get('total_count', 'N/A')}")
        print(f"  Returned count in details: {finding.details.get('returned_count', 'N/A')}")
        print(f"  Number of entities: {len(finding.details.get('entities', []))}")
        
        # Print first few entities
        entities = finding.details.get('entities', [])
        if entities:
            print(f"  First 3 entities:")
            for i, e in enumerate(entities[:3]):
                print(f"    {i+1}. {e.get('fullyQualifiedName')}")


if __name__ == "__main__":
    test_query_building()
    print("\nAll tests passed!")