"""
State management for the OpenMetaMind swarm.

This module defines the data structures for the blackboard, agent findings,
conflicts, proposed actions, and overall swarm state.
"""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, TypedDict, Annotated
from uuid import uuid4

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
import operator


class FindingType(str, Enum):
    """Types of findings that agents can produce."""
    CLASSIFICATION = "classification"
    QUALITY = "quality"
    COMPLIANCE = "compliance"
    OWNERSHIP = "ownership"
    DESCRIPTION = "description"
    LINEAGE = "lineage"
    OTHER = "other"


class ActionType(str, Enum):
    """Types of actions that can be proposed and executed."""
    ASSIGN_TAG = "assign_tag"
    UPDATE_OWNER = "update_owner"
    ADD_DESCRIPTION = "add_description"
    CREATE_GLOSSARY_TERM = "create_glossary_term"
    UPDATE_LINEAGE = "update_lineage"
    ADD_OWNER = "add_owner"
    REMOVE_OWNER = "remove_owner"
    DELETE_TAG = "delete_tag"
    OTHER = "other"


class MCPToolCall(BaseModel):
    """Record of an MCP tool call for audit trails."""
    tool_name: str
    parameters: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    success: bool = True
    error: Optional[str] = None


class ProposedAction(BaseModel):
    """A proposed action to be executed by the Action Executor."""
    action_type: ActionType
    entity_fqn: str  # Fully qualified name of the OpenMetadata entity
    parameters: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this action")
    proposed_by: str  # agent_id that proposed this action
    proposed_at: datetime = Field(default_factory=datetime.utcnow)


class AgentFinding(BaseModel):
    """
    A finding produced by an agent during execution.
    
    Findings are append-only and stored in the blackboard.
    """
    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_id: str
    subtask_id: str
    task_description: str
    
    # The actual output
    finding_type: FindingType
    target_entity: Optional[str] = None  # FQN of table/column/etc
    summary: str  # Human-readable summary
    details: Dict[str, Any] = Field(default_factory=dict)  # Structured data
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this finding")
    
    # Proposed actions (if any)
    proposed_actions: List[ProposedAction] = Field(default_factory=list)
    
    # Raw evidence
    mcp_tool_calls: List[MCPToolCall] = Field(default_factory=list)
    llm_reasoning: Optional[str] = None  # Chain-of-thought (for audit)


class Conflict(BaseModel):
    """A conflict detected by the Integrity Critic between findings."""
    conflict_id: str = Field(default_factory=lambda: str(uuid4()))
    finding_ids: List[str]  # Which findings conflict
    agents_involved: List[str]
    description: str  # "Agent A says X, Agent B says not-X"
    severity: str = Field(default="warning", pattern="^(warning|critical)$")  # warning, critical
    resolution: Optional[str] = None  # How Integrity Critic resolved it
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None # agent_id or "human"


class CriticDecision(str, Enum):
    """Decision made by the Integrity Critic."""
    AUTO_APPROVE = "auto_approve"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    REJECT_AND_RETRY = "reject_and_retry"


class FindingAssessment(BaseModel):
    """Assessment of a finding by the Integrity Critic."""
    finding_id: str
    validity_score: float = Field(ge=0.0, le=1.0)
    assessment_reason: str = ""
    is_consistent_with_others: bool = True
    has_sufficient_evidence: bool = False
    mcp_calls_verified: bool = False


class CriticReview(BaseModel):
    """Complete review result from the Integrity Critic."""
    findings_reviewed: int
    conflicts_detected: int
    finding_assessments: List[FindingAssessment] = Field(default_factory=list)
    decision: CriticDecision
    reasoning: str = ""
    conflicts_resolved: int = 0
    conflicts_escalated: int = 0
    approved_actions: List[ProposedAction] = Field(default_factory=list)
    rejected_actions: List[ProposedAction] = Field(default_factory=list)
    escalated_actions: List[ProposedAction] = Field(default_factory=list)
    summary: str = ""


class AgentStatus(str, Enum):
    """Status of an agent in the swarm."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


# Blackboard State - Append-only event log
BlackboardState = TypedDict(
    "BlackboardState",
    {
        "findings": Annotated[List[AgentFinding], operator.add],
        "conflicts": Annotated[List[Conflict], operator.add],
        "agent_statuses": Dict[str, AgentStatus],
        "execution_phase": str,  # planning, executing, reviewing, awaiting_approval, completed
    },
)

# Overall Swarm State
SwarmState = TypedDict(
    "SwarmState",
    {
        "blackboard": BlackboardState,
        "execution_plan": Optional[Dict[str, Any]],  # Will be ExecutionPlan model
        "completed_subtasks": List[str],
        "current_parallel_group": List[str],
        "user_query": str,
        "user_input": str,  # Keeping for backward compatibility
        "coordinator_notes": Optional[str],
        "conversation_history": List[BaseMessage],
        "delegated_task": Optional[str],
        "coordinator_response": Optional[str],
        "critic_review": Optional[Dict[str, Any]],
        "approved_actions": List[Dict[str, Any]],
        "execution_results": Optional[Dict[str, Any]],
        "executed_actions": List[str],  # List of action hashes that have been executed (for idempotency)
    },
)