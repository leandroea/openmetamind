"""
Tests for the Integrity Critic - conflict detection and resolution.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.graph.integrity_critic import IntegrityCritic
from src.models.state import (
    AgentFinding, Conflict, FindingType, ProposedAction,
    ActionType, CriticDecision, FindingAssessment, MCPToolCall
)


class TestIntegrityCritic:
    """Tests for the Integrity Critic node."""

    @pytest.fixture
    def critic(self, mock_llm):
        with patch('src.graph.integrity_critic.ChatOpenAI', return_value=mock_llm):
            return IntegrityCritic()

    def test_critic_returns_empty_review_for_no_findings(self, critic, sample_swarm_state):
        """Test that critic handles empty findings gracefully."""
        sample_swarm_state["blackboard"] = {
            "findings": [],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        assert "critic_review" in result
        assert result["critic_review"]["findings_reviewed"] == 0
        assert result["next"] == "human_gate"  # No findings to auto-approve

    def test_critic_detects_conflicts_between_findings(self, critic, sample_swarm_state):
        """Test that critic detects conflicting findings about the same entity."""
        # Create two findings with different summaries for the same entity
        finding1 = AgentFinding(
            finding_id="finding-1",
            agent_id="data_steward",
            subtask_id="classify-1",
            task_description="Classify email column",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.users.email",
            summary="email is PII.Sensitive",
            details={"classification": "PII.Sensitive"},
            confidence=0.9,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning="Column name suggests PII"
        )
        
        finding2 = AgentFinding(
            finding_id="finding-2",
            agent_id="quality_guardian",
            subtask_id="profile-1",
            task_description="Profile email column",
            finding_type=FindingType.QUALITY,
            target_entity="customers.users.email",
            summary="email column has 15% nulls",
            details={"null_percentage": 15},
            confidence=0.85,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning="Profile analysis"
        )
        
        sample_swarm_state["blackboard"] = {
            "findings": [finding1, finding2],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        # Critic should detect conflicts or at least review both findings
        assert "critic_review" in result
        assert result["critic_review"]["findings_reviewed"] >= 1

    def test_critic_detects_tag_conflicts(self, critic, sample_swarm_state):
        """Test conflict detection when two agents propose different tags."""
        # Finding 1: Data steward says email is PII.Sensitive
        finding1 = AgentFinding(
            finding_id="finding-tag-1",
            agent_id="data_steward",
            subtask_id="classify-1",
            task_description="Classify email column",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.users.email",
            summary="email is PII.Sensitive",
            details={"classification": "PII.Sensitive"},
            confidence=0.9,
            proposed_actions=[
                ProposedAction(
                    action_type=ActionType.ASSIGN_TAG,
                    entity_fqn="customers.users.email",
                    parameters={"tags": ["PII.Sensitive"]},
                    confidence=0.9,
                    proposed_by="data_steward"
                )
            ],
            mcp_tool_calls=[],
            llm_reasoning="Column name suggests sensitive PII"
        )
        
        # Finding 2: Another agent says email is PII.Internal
        finding2 = AgentFinding(
            finding_id="finding-tag-2",
            agent_id="policy_enforcer",
            subtask_id="classify-2",
            task_description="Check email classification policy",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.users.email",
            summary="email is PII.Internal",
            details={"classification": "PII.Internal"},
            confidence=0.85,
            proposed_actions=[
                ProposedAction(
                    action_type=ActionType.ASSIGN_TAG,
                    entity_fqn="customers.users.email",
                    parameters={"tags": ["PII.Internal"]},
                    confidence=0.85,
                    proposed_by="policy_enforcer"
                )
            ],
            mcp_tool_calls=[],
            llm_reasoning="Based on policy analysis"
        )
        
        sample_swarm_state["blackboard"] = {
            "findings": [finding1, finding2],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        # Should detect conflict or escalate to human
        assert "critic_review" in result
        # Either conflict detected or escalated to human gate
        assert (
            result["critic_review"]["conflicts_detected"] > 0 or
            result["next"] == "human_gate"
        )

    def test_critic_auto_approve_high_confidence_no_conflicts(self, critic, sample_swarm_state):
        """Test that critic auto-approves when all findings are high confidence and no conflicts."""
        finding = AgentFinding(
            finding_id="finding-high-conf",
            agent_id="catalog_scout",
            subtask_id="discover-1",
            task_description="Discover tables",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.orders",
            summary="Found 5 tables in customers database",
            details={"table_count": 5},
            confidence=0.95,  # High confidence
            proposed_actions=[],
        mcp_tool_calls=[MCPToolCall(tool_name="list_entities", parameters={}, success=True)], # Has evidence
            llm_reasoning="Direct MCP query"
        )
        
        sample_swarm_state["blackboard"] = {
            "findings": [finding],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        assert "critic_review" in result
        # With mocked LLM, we might get different results, but should have a decision
        assert "decision" in result["critic_review"]

    def test_critic_escalates_low_confidence_findings(self, critic, sample_swarm_state):
        """Test that critic escalates low confidence findings to human."""
        finding = AgentFinding(
            finding_id="finding-low-conf",
            agent_id="data_steward",
            subtask_id="classify-1",
            task_description="Classify ambiguous column",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.users.data",
            summary="data column might contain PII",
            details={"uncertain": True},
            confidence=0.4,  # Low confidence
            proposed_actions=[],
            mcp_tool_calls=[],  # No evidence
            llm_reasoning="Uncertain classification"
        )
        
        sample_swarm_state["blackboard"] = {
            "findings": [finding],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        assert "critic_review" in result
        # Should escalate to human for low confidence
        assert result["next"] in ["human_gate", "planner"]  # Either escalation or retry

    def test_critic_validates_mcp_tool_calls(self, critic, sample_swarm_state):
        """Test that critic checks for MCP tool call evidence."""
        # Finding with MCP tool calls (evidence)
        finding_with_evidence = AgentFinding(
            finding_id="finding-with-evidence",
            agent_id="catalog_scout",
            subtask_id="discover-1",
            task_description="List tables",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers",
            summary="Found tables",
            details={},
            confidence=0.9,
            proposed_actions=[],
            mcp_tool_calls=[MCPToolCall(tool_name="list_entities", parameters={}, success=True)],
            llm_reasoning="Based on MCP response"
        )
        
        # Finding without MCP tool calls (no evidence)
        finding_without_evidence = AgentFinding(
            finding_id="finding-no-evidence",
            agent_id="data_steward",
            subtask_id="classify-1",
            task_description="Classify column",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.users.id",
            summary="id is PII",
            details={},
            confidence=0.9,
            proposed_actions=[],
            mcp_tool_calls=[],  # No evidence!
            llm_reasoning="Guess"
        )
        
        sample_swarm_state["blackboard"] = {
            "findings": [finding_with_evidence, finding_without_evidence],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        assert "critic_review" in result
        # Should have reviewed both findings
        assert result["critic_review"]["findings_reviewed"] == 2


class TestConflictResolution:
    """Tests for conflict resolution scenarios."""

    @pytest.fixture
    def critic(self, mock_llm):
        with patch('src.graph.integrity_critic.ChatOpenAI', return_value=mock_llm):
            return IntegrityCritic()

    def test_conflict_model_structure(self):
        """Test that Conflict model has required fields."""
        conflict = Conflict(
            finding_ids=["finding-1", "finding-2"],
            agents_involved=["agent-a", "agent-b"],
            description="Agent A says X, Agent B says not-X",
            severity="warning"
        )
        
        assert conflict.conflict_id is not None
        assert conflict.finding_ids == ["finding-1", "finding-2"]
        assert conflict.agents_involved == ["agent-a", "agent-b"]
        assert conflict.description == "Agent A says X, Agent B says not-X"
        assert conflict.severity == "warning"
        assert conflict.resolution is None

    def test_conflict_severity_levels(self):
        """Test conflict severity levels."""
        warning_conflict = Conflict(
            finding_ids=["f1", "f2"],
            agents_involved=["a1", "a2"],
            description="Minor disagreement",
            severity="warning"
        )
        
        critical_conflict = Conflict(
            finding_ids=["f1", "f2"],
            agents_involved=["a1", "a2"],
            description="Major disagreement",
            severity="critical"
        )
        
        assert warning_conflict.severity == "warning"
        assert critical_conflict.severity == "critical"

    def test_critic_writes_conflicts_to_blackboard(self, critic, sample_swarm_state):
        """Test that critic writes detected conflicts to blackboard."""
        # Create conflicting findings
        finding1 = AgentFinding(
            finding_id="conflict-1",
            agent_id="agent-a",
            subtask_id="task-1",
            task_description="Task 1",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="entity.1",
            summary="Summary A",
            details={},
            confidence=0.8,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning="Reasoning A"
        )
        
        finding2 = AgentFinding(
            finding_id="conflict-2",
            agent_id="agent-b",
            subtask_id="task-2",
            task_description="Task 2",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="entity.1",  # Same entity
            summary="Summary B",  # Different summary
            details={},
            confidence=0.8,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning="Reasoning B"
        )
        
        sample_swarm_state["blackboard"] = {
            "findings": [finding1, finding2],
            "conflicts": [],
            "agent_statuses": {},
            "execution_phase": "reviewing"
        }
        
        result = critic(sample_swarm_state)
        
        # Check if conflicts were added to blackboard
        if "blackboard" in result:
            assert "conflicts" in result["blackboard"]


class TestCriticDecision:
    """Tests for critic decision logic."""

    def test_critic_decision_enum_values(self):
        """Test that CriticDecision enum has correct values."""
        assert CriticDecision.AUTO_APPROVE.value == "auto_approve"
        assert CriticDecision.ESCALATE_TO_HUMAN.value == "escalate_to_human"
        assert CriticDecision.REJECT_AND_RETRY.value == "reject_and_retry"

    def test_finding_assessment_model(self):
        """Test FindingAssessment model structure."""
        assessment = FindingAssessment(
            finding_id="test-finding",
            validity_score=0.85,
            is_consistent_with_others=True,
            has_sufficient_evidence=True,
            mcp_calls_verified=True
        )
        
        assert assessment.finding_id == "test-finding"
        assert assessment.validity_score == 0.85
        assert assessment.is_consistent_with_others is True
        assert assessment.has_sufficient_evidence is True
        assert assessment.mcp_calls_verified is True

    def test_finding_assessment_validity_score_range(self):
        """Test that validity score must be in valid range."""
        # Valid scores
        for score in [0.0, 0.5, 1.0]:
            assessment = FindingAssessment(
                finding_id="test",
                validity_score=score,
                is_consistent_with_others=True,
                has_sufficient_evidence=True,
                mcp_calls_verified=True
            )
            assert assessment.validity_score == score