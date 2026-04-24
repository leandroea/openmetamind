"""
Agent Registry for the OpenMetaMind swarm.

Implements a plugin system where agents self-register on import.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
import logging

from .base import SwarmAgent, Capability
from ..models.state import AgentFinding

logger = logging.getLogger(__name__)


@dataclass
class AgentMatch:
    """Represents an agent matched to a task with a confidence score."""
    agent: SwarmAgent
    confidence: float


class AgentRegistry:
    """
    Singleton registry for SwarmAgent implementations.
    
    Agents self-register on import via the register() method.
    """
    
    _instance: Optional["AgentRegistry"] = None
    _agents: Dict[str, SwarmAgent] = {}
    
    def __new__(cls) -> "AgentRegistry":
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the registry (only called once due to singleton)."""
        if not hasattr(self, '_initialized'):
            self._agents = {}
            self._initialized = True
    
    def register(self, agent: SwarmAgent) -> None:
        """
        Register an agent in the registry.
        
        Agents should call this in their module's global scope:
            registry = AgentRegistry()
            registry.register(MyAgent())
        """
        if agent.agent_id in self._agents:
            logger.warning(f"Agent {agent.agent_id} is already registered. Overwriting.")
        
        self._agents[agent.agent_id] = agent
        logger.info(f"Registered agent: {agent.agent_id} ({agent.display_name})")
    
    def get_agent(self, agent_id: str) -> Optional[SwarmAgent]:
        """Get an agent by its ID."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> List[SwarmAgent]:
        """List all registered agents."""
        return list(self._agents.values())
    
    def list_all_agents(self) -> List[Dict[str, Any]]:
        """
        Get detailed metadata for all registered agents.
        
        Returns a list of dictionaries containing:
        - agent_id: Unique identifier
        - display_name: Human-readable name
        - description: What the agent does
        - emoji: Avatar emoji for UI
        - capabilities: List of capability details
        """
        result = []
        for agent in self._agents.values():
            capabilities = []
            for cap in agent.capabilities:
                capabilities.append({
                    "name": cap.name,
                    "description": cap.description
                })
            result.append({
                "agent_id": agent.agent_id,
                "display_name": agent.display_name,
                "description": agent.description,
                "emoji": agent.avatar_emoji,
                "capabilities": capabilities
            })
        return result
    
    def format_roster(self) -> str:
        """
        Format the agent roster as a human-readable team description.
        
        Returns a formatted string that reads like a team roster with
        emojis, names, and capability summaries.
        """
        agents = self.list_all_agents()
        if not agents:
            return "I don't have any agents on my team yet."
        
        lines = ["📋 **My Team**\n"]
        for agent in agents:
            lines.append(f"{agent['emoji']} **{agent['display_name']}** (`{agent['agent_id']}`)")
            lines.append(f"   {agent['description']}")
            if agent['capabilities']:
                cap_list = ", ".join([c['name'] for c in agent['capabilities']])
                lines.append(f"   Can do: {cap_list}")
            lines.append("")  # Empty line between agents
        
        lines.append("---")
        lines.append("💡 Feel free to assign me a task! I can help you explore your data, "
                      "manage governance, check quality, and more.")
        
        return "\n".join(lines)
    
    def find_agents_for_task(
        self, 
        task: str, 
        min_confidence: float = 0.6
    ) -> List[AgentMatch]:
        """
        Find agents that can handle a given task.
        
        Uses simple keyword matching for now. LLM-based routing comes later.
        
        Args:
            task: The task description to match against
            min_confidence: Minimum confidence score to include agent (default: 0.6)
            
        Returns:
            List of AgentMatch objects sorted by confidence (highest first)
        """
        matches = []
        task_lower = task.lower()
        
        for agent in self._agents.values():
            # Use the agent's can_handle method to get confidence score
            # Note: This is async, but we're calling it synchronously for simplicity
            # In a real implementation, this would be handled async by the planner
            try:
                import asyncio
                # Try to get the running loop, if none, create a new one
                try:
                    loop = asyncio.get_running_loop()
                    # If we're already in an async context, we need to schedule the coroutine
                    # For simplicity in this scaffold, we'll run it in a new thread
                    # In production, the planner would handle this properly
                    confidence = 0.0  # Placeholder - would be awaited properly
                except RuntimeError:
                    # No running loop, we can create a new one
                    confidence = asyncio.run(agent.can_handle(task))
            except Exception as e:
                logger.warning(f"Error checking if agent {agent.agent_id} can handle task: {e}")
                confidence = 0.0
            
            if confidence >= min_confidence:
                matches.append(AgentMatch(agent=agent, confidence=confidence))
        
        # Sort by confidence descending
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches
    
    def format_capabilities(self) -> str:
        """
        Format all agent capabilities for use in Coordinator prompts.
        
        Returns a string describing what each agent can do.
        """
        lines = ["Available agents and their capabilities:"]
        for agent in self._agents.values():
            lines.append(f"- {agent.display_name} ({agent.agent_id}): {agent.description}")
            if agent.capabilities:
                cap_names = [cap.name for cap in agent.capabilities]
                lines.append(f"  Capabilities: {', '.join(cap_names)}")
        return "\n".join(lines)


# Global registry instance for convenience
registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    return registry