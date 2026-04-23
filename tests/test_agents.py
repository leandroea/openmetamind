"""
Unit tests for OpenMetaMind agents.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.agents.catalog_scout import CatalogScout
from src.agents.data_steward import DataSteward
from src.agents.quality_guardian import QualityGuardian
from src.agents.example_agent import ExampleAgent
from src.models.state import AgentFinding, FindingType, ProposedAction, ActionType


class TestCatalogScout:
    """Tests for the CatalogScout agent."""

    @pytest.fixture
    def agent(self):
        return CatalogScout()

    @pytest.mark.asyncio
    async def test_can_handle_discovery_task(self, agent):
        """Test that agent can handle discovery tasks."""
        score = await agent.can_handle("list tables in customers database")
        assert 0.0 <= score <= 1.0
        assert score > 0.0  # Should recognize discovery keywords

    @pytest.mark.asyncio
    async def test_can_handle_non_discovery_task(self, agent):
        """Test that agent returns low score for non-discovery tasks."""
        score = await agent.can_handle("analyze data quality")
        assert 0.0 <= score <= 1.0
        # Should return lower score for non-discovery tasks

    @pytest.mark.asyncio
    async def test_execute_returns_finding(self, agent, mock_mcp_client):
        """Test that execute returns a valid AgentFinding."""
        mock_mcp_client.list_entities = AsyncMock(return_value=[])
        
        finding = await agent.execute(
            task="list tables",
            inputs={},
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert finding.agent_id == "catalog_scout"
        assert finding.confidence >= 0.0
        assert finding.confidence <= 1.0
        assert finding.finding_type == FindingType.CLASSIFICATION

    @pytest.mark.asyncio
    async def test_execute_with_entities(self, agent, mock_mcp_client):
        """Test execute with mock entity data."""
        mock_entities = [
            MagicMock(
                name="users",
                fullyQualifiedName="customers.users",
                description="User table"
            ),
            MagicMock(
                name="orders",
                fullyQualifiedName="customers.orders",
                description="Orders table"
            )
        ]
        mock_mcp_client.list_entities = AsyncMock(return_value=mock_entities)
        mock_mcp_client.__aenter__ = AsyncMock(return_value=mock_mcp_client)
        mock_mcp_client.__aexit__ = AsyncMock(return_value=None)
        
        finding = await agent.execute(
            task="list tables",
            inputs={},
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert "2" in finding.summary  # Should mention 2 entities
        assert finding.confidence > 0.0


class TestDataSteward:
    """Tests for the DataSteward agent."""

    @pytest.fixture
    def agent(self):
        return DataSteward()

    @pytest.mark.asyncio
    async def test_can_handle_classification_task(self, agent):
        """Test that agent can handle classification tasks."""
        score = await agent.can_handle("detect PII in customer data")
        assert 0.0 <= score <= 1.0
        assert score > 0.0  # Should recognize classification keywords

    @pytest.mark.asyncio
    async def test_execute_returns_finding(self, agent, mock_mcp_client):
        """Test that execute returns a valid AgentFinding."""
        mock_mcp_client.get_table_profile = AsyncMock(return_value=MagicMock(
            tableName="users",
            databaseName="customers",
            columnCount=10
        ))
        
        finding = await agent.execute(
            task="classify PII columns",
            inputs={"entity_fqn": "customers.users"},
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert finding.agent_id == "data_steward"
        assert finding.confidence >= 0.0
        assert finding.confidence <= 1.0
        assert finding.finding_type == FindingType.CLASSIFICATION

    @pytest.mark.asyncio
    async def test_execute_without_entity_returns_error_finding(self, agent, mock_mcp_client):
        """Test that execute without entity returns error finding."""
        finding = await agent.execute(
            task="classify data",
            inputs={},  # No entity_fqn
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert finding.confidence == 0.0
        assert "No entity" in finding.summary


class TestQualityGuardian:
    """Tests for the QualityGuardian agent."""

    @pytest.fixture
    def agent(self):
        return QualityGuardian()

    @pytest.mark.asyncio
    async def test_can_handle_quality_task(self, agent):
        """Test that agent can handle quality tasks."""
        score = await agent.can_handle("analyze data quality and detect anomalies")
        assert 0.0 <= score <= 1.0
        assert score > 0.0  # Should recognize quality keywords

    @pytest.mark.asyncio
    async def test_execute_returns_finding(self, agent, mock_mcp_client):
        """Test that execute returns a valid AgentFinding."""
        mock_mcp_client.get_table_profile = AsyncMock(return_value=MagicMock(
            tableName="orders",
            databaseName="customers",
            columnCount=15,
            rowCount=5000
        ))
        
        finding = await agent.execute(
            task="profile table quality",
            inputs={"table_fqn": "customers.orders"},
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert finding.agent_id == "quality_guardian"
        assert finding.confidence >= 0.0
        assert finding.confidence <= 1.0
        assert finding.finding_type == FindingType.QUALITY

    @pytest.mark.asyncio
    async def test_execute_without_table_returns_error_finding(self, agent, mock_mcp_client):
        """Test that execute without table returns error finding."""
        finding = await agent.execute(
            task="analyze quality",
            inputs={},  # No table_fqn
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert finding.confidence == 0.0
        assert "No table" in finding.summary


class TestExampleAgent:
    """Tests for the ExampleAgent."""

    @pytest.fixture
    def agent(self):
        return ExampleAgent()

    @pytest.mark.asyncio
    async def test_can_handle_example_task(self, agent):
        """Test that agent can handle example tasks."""
        score = await agent.can_handle("run an example demo")
        assert 0.0 <= score <= 1.0
        assert score > 0.0  # Should recognize "example" keyword

    @pytest.mark.asyncio
    async def test_execute_returns_finding(self, agent, mock_mcp_client):
        """Test that execute returns a valid AgentFinding."""
        finding = await agent.execute(
            task="run example task",
            inputs={},
            mcp_client=mock_mcp_client
        )
        
        assert isinstance(finding, AgentFinding)
        assert finding.agent_id == "example_agent"
        assert finding.confidence == 0.95  # Example agent has high confidence
        assert finding.finding_type == FindingType.OTHER


class TestAgentConfidence:
    """Tests for confidence score validation across all agents."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_class", [CatalogScout, DataSteward, QualityGuardian, ExampleAgent])
    async def test_confidence_in_valid_range(self, agent_class, mock_mcp_client):
        """Test that all agents return confidence in valid range [0.0, 1.0]."""
        agent = agent_class()
        
        # Execute with valid inputs
        if agent_class == DataSteward:
            inputs = {"entity_fqn": "test.table"}
        elif agent_class == QualityGuardian:
            inputs = {"table_fqn": "test.table"}
        else:
            inputs = {}
        
        finding = await agent.execute(
            task="test task",
            inputs=inputs,
            mcp_client=mock_mcp_client
        )
        
        assert 0.0 <= finding.confidence <= 1.0, \
            f"{agent_class.__name__} returned invalid confidence: {finding.confidence}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_class", [CatalogScout, DataSteward, QualityGuardian, ExampleAgent])
    async def test_can_handle_returns_valid_score(self, agent_class):
        """Test that can_handle returns score in valid range [0.0, 1.0]."""
        agent = agent_class()
        
        score = await agent.can_handle("test task description")
        
        assert 0.0 <= score <= 1.0, \
            f"{agent_class.__name__} returned invalid score: {score}"


class TestAgentFindingStructure:
    """Tests for AgentFinding structure validation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_class", [CatalogScout, DataSteward, QualityGuardian, ExampleAgent])
    async def test_finding_has_required_fields(self, agent_class, mock_mcp_client):
        """Test that all agent findings have required fields."""
        agent = agent_class()
        
        # Execute with valid inputs
        if agent_class == DataSteward:
            inputs = {"entity_fqn": "test.table"}
        elif agent_class == QualityGuardian:
            inputs = {"table_fqn": "test.table"}
        else:
            inputs = {}
        
        finding = await agent.execute(
            task="test task",
            inputs=inputs,
            mcp_client=mock_mcp_client
        )
        
        # Check required fields exist
        assert hasattr(finding, 'finding_id')
        assert hasattr(finding, 'timestamp')
        assert hasattr(finding, 'agent_id')
        assert hasattr(finding, 'subtask_id')
        assert hasattr(finding, 'task_description')
        assert hasattr(finding, 'finding_type')
        assert hasattr(finding, 'summary')
        assert hasattr(finding, 'details')
        assert hasattr(finding, 'confidence')
        assert hasattr(finding, 'proposed_actions')
        assert hasattr(finding, 'mcp_tool_calls')
        
        # Check types
        assert isinstance(finding.finding_id, str)
        assert isinstance(finding.timestamp, datetime)
        assert isinstance(finding.agent_id, str)
        assert isinstance(finding.summary, str)
        assert isinstance(finding.details, dict)
        assert isinstance(finding.proposed_actions, list)
        assert isinstance(finding.mcp_tool_calls, list)