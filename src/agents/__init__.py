"""
Agents module for OpenMetaMind.
"""

from .base import SwarmAgent, Capability
from .registry import AgentRegistry, get_agent_registry, AgentMatch
from . import catalog_scout, data_steward, quality_guardian, example_agent, documentation_agent  # Import to trigger agent registration

__all__ = [
    "SwarmAgent",
    "Capability",
    "AgentRegistry",
    "get_agent_registry",
    "AgentMatch",
    "catalog_scout",
    "data_steward",
    "quality_guardian",
    "example_agent",
    "documentation_agent",
]