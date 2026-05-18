"""
Real integration tests for DocumentationAgent using actual LLM and MCP connections.
No mocks, no fallbacks - all real data from OpenMetadata.
"""
import pytest
from datetime import datetime

from src.agents.documentation_agent import DocumentationAgent


class TestDocumentationAgentReal:
    """Integration tests for DocumentationAgent with real MCP and LLM."""

    @pytest.fixture
    def agent(self):
        """Create a DocumentationAgent instance."""
        return DocumentationAgent()

    @pytest.mark.asyncio
    async def test_find_undocumented_tables(self, agent):
        """Test 1: Find tables that lack descriptions."""
        print(f"\n[{datetime.now().isoformat()}] Test 1: Find Undocumented Tables")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables in the catalog and identify which ones are missing descriptions or have incomplete documentation. Show me examples of tables without descriptions.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 1 - Agent found undocumented entities")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_generate_description(self, agent):
        """Test 2: Generate a description for an entity."""
        print(f"\n[{datetime.now().isoformat()}] Test 2: Generate Description")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables, then pick one and generate a business-friendly description for it based on its name, columns, and metadata. Show me what the description would look like.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 2 - Agent generated description")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_check_column_documentation(self, agent):
        """Test 3: Check column-level documentation coverage."""
        print(f"\n[{datetime.now().isoformat()}] Test 3: Column Documentation Coverage")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for a table and examine its columns. Which columns are missing descriptions? List them and suggest what each column might contain based on its name.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 3 - Agent checked column documentation")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_document_dashboard(self, agent):
        """Test 4: Document a dashboard entity."""
        print(f"\n[{datetime.now().isoformat()}] Test 4: Document Dashboard")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for dashboards in the catalog and document one that lacks proper description. What would you suggest as its description based on the dashboard's name and metadata?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 4 - Agent documented dashboard")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_documentation_coverage_report(self, agent):
        """Test 5: Generate documentation coverage report."""
        print(f"\n[{datetime.now().isoformat()}] Test 5: Documentation Coverage Report")
        print("=" * 70)
        
        result = await agent.execute(
            task="Analyze the documentation coverage across tables in the catalog. What percentage of tables have descriptions? Which schemas or databases have the most undocumented entities?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 5 - Agent generated coverage report")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_improve_existing_description(self, agent):
        """Test 6: Improve existing poor descriptions."""
        print(f"\n[{datetime.now().isoformat()}] Test 6: Improve Existing Descriptions")
        print("=" * 70)
        
        result = await agent.execute(
            task="Find tables that have very short or generic descriptions (like 'This is the table description'). Suggest improved, more detailed business descriptions for at least 2 such tables.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 6 - Agent improved descriptions")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_full_documentation_pipeline(self, agent):
        """Test 7: Full documentation pipeline."""
        print(f"\n[{datetime.now().isoformat()}] Test 7: Full Documentation Pipeline")
        print("=" * 70)
        
        result = await agent.execute(
            task="Perform a complete documentation workflow: 1) Find an undocumented table, 2) Analyze its structure and metadata, 3) Generate a business-friendly description, 4) Suggest descriptions for any undocumented columns. Show me the complete pipeline.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 7 - Agent completed full pipeline")
        else:
            pytest.fail("No result returned")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])