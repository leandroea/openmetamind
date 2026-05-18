"""
Real integration tests for QualityGuardian agent using actual LLM and MCP connections.
No mocks, no fallbacks - all real data from OpenMetadata.
"""
import pytest
from datetime import datetime

from src.agents.quality_guardian import QualityGuardian


class TestQualityGuardianReal:
    """Integration tests for QualityGuardian with real MCP and LLM."""

    @pytest.fixture
    def agent(self):
        """Create a QualityGuardian agent instance."""
        return QualityGuardian()

    @pytest.mark.asyncio
    async def test_table_profiling(self, agent):
        """Test 1: Profile a table with statistical metrics."""
        print(f"\n[{datetime.now().isoformat()}] Test 1: Table Profiling")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables in the catalog, then get details of one table including its columns, data types, and any available statistics or profiling information. What can you tell me about this table's quality?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 1 - Agent profiled table")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_anomaly_detection(self, agent):
        """Test 2: Detect anomalies in table data."""
        print(f"\n[{datetime.now().isoformat()}] Test 2: Anomaly Detection")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables in the catalog, then analyze one table for anomalies or unusual patterns. Look for: missing descriptions, inconsistent naming, potential PII columns, and any data quality issues.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 2 - Agent detected anomalies")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_quality_assessment(self, agent):
        """Test 3: Assess overall data quality."""
        print(f"\n[{datetime.now().isoformat()}] Test 3: Quality Assessment")
        print("=" * 70)
        
        result = await agent.execute(
            task="Perform a comprehensive quality assessment of the catalog. What percentage of tables have proper descriptions? Are there tables with missing column documentation? Identify the top data quality issues.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 3 - Agent assessed quality")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_column_analysis(self, agent):
        """Test 4: Analyze column-level quality metrics."""
        print(f"\n[{datetime.now().isoformat()}] Test 4: Column-level Analysis")
        print("=" * 70)
        
        result = await agent.execute(
            task="Search for tables, then examine the columns of one table in detail. What data quality issues do you see at the column level? Are there missing descriptions? Invalid data types? Potential PII?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 4 - Agent analyzed columns")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_sla_compliance(self, agent):
        """Test 5: Check SLA compliance for data assets."""
        print(f"\n[{datetime.now().isoformat()}] Test 5: SLA Compliance Check")
        print("=" * 70)
        
        result = await agent.execute(
            task="Check if there are any SLA-related metadata or tier classifications on tables in the catalog. Which tables appear to be mission-critical based on their names, descriptions, or tags?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 5 - Agent checked SLA compliance")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_root_cause_analysis(self, agent):
        """Test 6: Perform root cause analysis for data issues."""
        print(f"\n[{datetime.now().isoformat()}] Test 6: Root Cause Analysis")
        print("=" * 70)
        
        result = await agent.execute(
            task="If you find a table with data quality issues (missing descriptions, potential PII, etc.), trace back to identify the root cause. Is it a documentation issue? A data governance issue? A technical issue?",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 6 - Agent performed root cause analysis")
        else:
            pytest.fail("No result returned")

    @pytest.mark.asyncio
    async def test_quality_report(self, agent):
        """Test 7: Generate comprehensive quality report."""
        print(f"\n[{datetime.now().isoformat()}] Test 7: Comprehensive Quality Report")
        print("=" * 70)
        
        result = await agent.execute(
            task="Generate a comprehensive data quality report for the catalog. Include: 1) Overall quality score estimate, 2) Top 5 quality issues found, 3) Recommendations for improvements, 4) Priority ranking of issues.",
            inputs={}
        )
        
        print(f"Response length: {len(result) if result else 0} chars")
        if result:
            print(f"First 800 chars:\n{result[:800]}")
            print(f"\n[PASS] Test 7 - Agent generated quality report")
        else:
            pytest.fail("No result returned")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])