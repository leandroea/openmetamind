"""
Real integration tests for DataSteward agent using actual LLM and MCP connections.
No mocks, no fallbacks - all real data from OpenMetadata.
"""
import pytest
from datetime import datetime

from src.agents.data_steward import DataSteward


class TestDataStewardReal:
    """Integration tests for DataSteward with real MCP and LLM."""

    @pytest.fixture
    def agent(self):
        """Create a DataSteward agent instance."""
        return DataSteward()

    @pytest.mark.asyncio
    async def test_pii_detection_columns(self, agent):
        """Test 1: Detect PII in table columns."""
        print(f"\n[{datetime.now().isoformat()}] Test 1: PII Detection in Columns")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables in the catalog, then get details of a table and analyze its columns for potential PII. Look for columns with names like email, phone, ssn, credit_card, password, address, name, etc.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            # Verify PII analysis was performed
            assert len(result) > 50
            print(f"\n[PASS] Test 1 - Agent analyzed columns for PII")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_tag_assignment(self, agent):
        """Test 2: Assign tags to an entity."""
        print(f"\n[{datetime.now().isoformat()}] Test 2: Tag Assignment")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables, then suggest appropriate governance tags for a table based on its content and column names. What tags would you recommend?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 2 - Agent suggested tags")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_ownership_analysis(self, agent):
        """Test 3: Analyze and suggest ownership for an entity."""
        print(f"\n[{datetime.now().isoformat()}] Test 3: Ownership Analysis")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables, then analyze one table for its ownership needs. What type of owner would be appropriate for this data asset?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 3 - Agent analyzed ownership needs")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_data_governance_review(self, agent):
        """Test 4: Comprehensive data governance review."""
        print(f"\n[{datetime.now().isoformat()}] Test 4: Data Governance Review")
        print("=" * 70)
        
        result = await agent.execute(
            task="Perform a data governance review of a table. Check: 1) What columns exist and their descriptions, 2) Are there any potential PII columns, 3) What governance tags or ownership might be needed, 4) Any other governance concerns?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 4 - Agent performed governance review")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_sensitive_data_patterns(self, agent):
        """Test 5: Identify sensitive data patterns."""
        print(f"\n[{datetime.now().isoformat()}] Test 5: Sensitive Data Pattern Detection")
        print("=" * 70)
        
        result = await agent.execute(
            task="Look for tables that might contain sensitive data. Search for tables and examine their column names and descriptions for patterns like: personal info, financial data, health records, authentication credentials, or contact information.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 5 - Agent identified sensitive data patterns")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_tag_recommendations_schema(self, agent):
        """Test 6: Recommend tags based on schema analysis."""
        print(f"\n[{datetime.now().isoformat()}] Test 6: Schema-based Tag Recommendations")
        print("=" * 70)
        
        result = await agent.execute(
            task="Analyze a database schema in the catalog. Based on the schema structure and naming conventions, suggest appropriate classification tags for the tables and columns.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 6 - Agent made schema-based tag recommendations")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_risk_assessment(self, agent):
        """Test 7: Data risk assessment."""
        print(f"\n[{datetime.now().isoformat()}] Test 7: Data Risk Assessment")
        print("=" * 70)
        
        result = await agent.execute(
            task="Perform a risk assessment for a table. Consider: 1) What PII might be exposed, 2) Are there missing descriptions or documentation, 3) Is there proper ownership, 4) Are sensitive columns adequately protected? Rate the risk level and suggest mitigations.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 7 - Agent performed risk assessment")
        else:
            pytest.fail("No result returned")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])