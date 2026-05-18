"""
Unit tests for OpenMetaMind agents.

All tests use real MCP client connections to OpenMetadata.
"""

import pytest

from src.agents.catalog_scout import CatalogScout
from src.agents.data_steward import DataSteward
from src.agents.quality_guardian import QualityGuardian


class TestCatalogScout:
    """Tests for the CatalogScout agent."""

    @pytest.fixture
    def agent(self):
        return CatalogScout()

    @pytest.mark.asyncio
    async def test_execute_with_real_mcp(self, agent, real_mcp_client):
        """Test that execute with real MCP client returns a valid string response."""
        async with real_mcp_client as client:
            result = await agent.execute(
                task="list tables",
                inputs={},
                mcp_client=client
            )
        
        assert isinstance(result, str)
        assert len(result) > 0


class TestDataSteward:
    """Tests for the DataSteward agent."""

    @pytest.fixture
    def agent(self):
        return DataSteward()

    @pytest.mark.asyncio
    async def test_execute_with_real_mcp(self, agent, real_mcp_client):
        """Test that execute with real MCP client returns a valid string response."""
        async with real_mcp_client as client:
            result = await agent.execute(
                task="classify PII columns",
                inputs={"entity_fqn": "sample_data.ecommerce_db.shopify.raw_customer"},
                mcp_client=client
            )
        
        assert isinstance(result, str)
        assert len(result) > 0


class TestQualityGuardian:
    """Tests for the QualityGuardian agent."""

    @pytest.fixture
    def agent(self):
        return QualityGuardian()

    @pytest.mark.asyncio
    async def test_execute_with_real_mcp(self, agent, real_mcp_client):
        """Test that execute with real MCP client returns a valid string response."""
        async with real_mcp_client as client:
            result = await agent.execute(
                task="profile table quality",
                inputs={"table_fqn": "sample_data.ecommerce_db.shopify.raw_customer"},
                mcp_client=client
            )
        
        assert isinstance(result, str)
        assert len(result) > 0


class TestAgentStructure:
    """Tests for agent structure validation."""

    def test_catalog_scout_has_required_properties(self):
        """Test that CatalogScout has all required properties."""
        agent = CatalogScout()
        assert agent.agent_id == "catalog_scout"
        assert agent.display_name == "Catalog Scout"
        assert len(agent.capabilities) > 0

    def test_data_steward_has_required_properties(self):
        """Test that DataSteward has all required properties."""
        agent = DataSteward()
        assert agent.agent_id == "data_steward"
        assert agent.display_name == "Data Steward"
        assert len(agent.capabilities) > 0

    def test_quality_guardian_has_required_properties(self):
        """Test that QualityGuardian has all required properties."""
        agent = QualityGuardian()
        assert agent.agent_id == "quality_guardian"
        assert agent.display_name == "Quality Guardian"
        assert len(agent.capabilities) > 0