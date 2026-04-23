"""
Base classes for the OpenMetaMind swarm agents.

This module defines the abstract base class for all agents and the Capability dataclass.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from ..models.state import AgentFinding, MCPToolCall


@dataclass
class Capability:
    """Describes a capability that an agent can perform."""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema for input validation
    output_schema: Dict[str, Any]  # JSON Schema for output validation


class SwarmAgent(ABC):
    """
    Every agent in the swarm implements this interface.
    
    Agents are stateless and self-register in the AgentRegistry.
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier for the agent."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for display in UI."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description of what the agent does."""

    @property
    @abstractmethod
    def avatar_emoji(self) -> str:
        """Emoji used to represent the agent in the UI."""

    @property
    @abstractmethod
    def capabilities(self) -> List[Capability]:
        """List of capabilities this agent provides."""

    @property
    def default_confidence_threshold(self) -> float:
        """Default confidence threshold for considering an agent for a task."""
        return 0.8

    @property
    def requires_human_approval(self) -> bool:
        """
        If True, all actions from this agent go through human gate.
        Override in subclasses if needed.
        """
        return False

    @abstractmethod
    async def can_handle(self, task_description: str) -> float:
        """
        Return 0.0-1.0 confidence that this agent can handle the task.
        
        This method should be lightweight and fast, using keyword matching or
        embeddings to determine suitability.
        """
        ...

    @abstractmethod
    async def execute(
        self, 
        task: str, 
        inputs: Dict[str, Any], 
        mcp_client: Any  # Will be OpenMetadataMCPClient when imported
    ) -> AgentFinding:
        """
        Execute the agent's core logic.
        
        Args:
            task: The specific task description for this agent
            inputs: Dictionary of input data from the blackboard
            mcp_client: MCP client for interacting with OpenMetadata
            
        Returns:
            AgentFinding containing the results and any proposed actions
        """
        ...