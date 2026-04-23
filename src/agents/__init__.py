"""
Agents module for OpenMetaMind.
"""

from .base import SwarmAgent, Capability
from .registry import AgentRegistry, get_agent_registry, AgentMatch
from . import example_agent  # Import to trigger agent registration

__all__ = [
    "SwarmAgent",
    "Capability",
    "AgentRegistry",
    "get_agent_registry",
    "AgentMatch",
    "example_agent",
]