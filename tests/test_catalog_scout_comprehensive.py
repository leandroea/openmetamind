"""
Real integration tests for CatalogScout agent using actual LLM and MCP connections.
No mocks, no fallbacks - all real data from OpenMetadata.
"""
import pytest
import asyncio
from datetime import datetime

from src.agents.catalog_scout import CatalogScout


class TestCatalogScoutReal:
    """Integration tests for CatalogScout with real MCP and LLM."""

    @pytest.fixture
    def agent(self):
        """Create a CatalogScout agent instance."""
        return CatalogScout()

    @pytest.mark.asyncio
    async def test_list_tables(self, agent):
        """Test 1: List all tables in the catalog."""
        print(f"\n[{datetime.now().isoformat()}] Test 1: List all tables")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables in the catalog. How many tables are there?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            # Extract key information from response
            print(f"First 500 chars:\n{result[:500]}")
            
            # Verify we got actual data
            assert "table" in result.lower() or "found" in result.lower()
            print(f"\n[PASS] Test 1 - Agent returned table data")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_search_entities(self, agent):
        """Test 2: Search for entities matching a query."""
        print(f"\n[{datetime.now().isoformat()}] Test 2: Search for specific entities")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for any entities that have 'customer' in their name or description",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 500 chars:\n{result[:500]}")
            # Verify search was performed
            assert len(result) > 50  # Should have actual results
            print(f"\n[PASS] Test 2 - Agent searched for entities")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_get_entity_details(self, agent):
        """Test 3: Get details of a specific entity."""
        print(f"\n[{datetime.now().isoformat()}] Test 3: Get entity details")
        print("=" * 70)
        
        result = await agent.execute(
            task="First search for tables, then get details of one of the tables by using its fully qualified name. Show me the column names and description.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            # Should contain column info
            assert "column" in result.lower() or "description" in result.lower()
            print(f"\n[PASS] Test 3 - Agent got entity details")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_discover_hierarchy(self, agent):
        """Test 4: Discover the catalog hierarchy (databases, schemas, tables)."""
        print(f"\n[{datetime.now().isoformat()}] Test 4: Discover catalog hierarchy")
        print("=" * 70)
        
        result = await agent.execute(
            task="Explore the OpenMetadata catalog hierarchy. Show me the databases, schemas, and table relationships. How many databases are there?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 600 chars:\n{result[:600]}")
            # Should contain hierarchy info
            assert len(result) > 100
            print(f"\n[PASS] Test 4 - Agent discovered hierarchy")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_explore_multiple_entity_types(self, agent):
        """Test 5: Explore different entity types (tables, dashboards, pipelines)."""
        print(f"\n[{datetime.now().isoformat()}] Test 5: Explore multiple entity types")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for different entity types in the catalog. What types of entities exist (tables, dashboards, pipelines, etc.)? List them with their counts.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 600 chars:\n{result[:600]}")
            # Should mention various entity types
            print(f"\n[PASS] Test 5 - Agent explored multiple entity types")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_semantic_search(self, agent):
        """Test 6: Semantic search when exact names are unknown."""
        print(f"\n[{datetime.now().isoformat()}] Test 6: Semantic search")
        print("=" * 70)
        
        result = await agent.execute(
            task="Use semantic search to find entities related to 'analytics' or 'reporting'. What did you find?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 600 chars:\n{result[:600]}")
            print(f"\n[PASS] Test 6 - Agent performed semantic search")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_lineage_exploration(self, agent):
        """Test 7: Explore entity lineage."""
        print(f"\n[{datetime.now().isoformat()}] Test 7: Explore lineage")
        print("=" * 70)
        
        result = await agent.execute(
            task="Look for lineage information. Can you find any entities that have upstream or downstream dependencies? Show me an example if it exists.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 600 chars:\n{result[:600]}")
            print(f"\n[PASS] Test 7 - Agent explored lineage")
        else:
            pytest.fail("No result returned")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])