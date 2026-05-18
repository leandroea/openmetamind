"""
Agent Registry for the OpenMetaMind swarm.

Implements a plugin system where agents self-register on import.
"""

from typing import List, Dict, Optional, Any
import logging



logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Singleton registry for agents.
    
    Agents self-register on import via the register() method.
    """
    
    _instance: Optional["AgentRegistry"] = None
    _agents: Dict[str, Any] = {}
    
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
    
    def register(self, agent: Any) -> None:
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
    
    def get_agent(self, agent_id: str) -> Optional[Any]:
        """Get an agent by its ID."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> list:
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
                if isinstance(cap, dict):
                    capabilities.append({
                        "name": cap.get("name", ""),
                        "description": cap.get("description", "")
                    })
                else:
                    capabilities.append({
                        "name": getattr(cap, "name", ""),
                        "description": getattr(cap, "description", "")
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


# Global registry instance for convenience
registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    return registry