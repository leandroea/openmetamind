"""
Agents module for OpenMetaMind.
"""


from .registry import AgentRegistry, get_agent_registry
from . import catalog_scout, data_steward, quality_guardian, documentation_agent  # Import to trigger agent registration

__all__ = [
    "AgentRegistry",
    "get_agent_registry",
    "catalog_scout",
    "data_steward",
    "quality_guardian",
    "documentation_agent",
]

# Import Orchestrator at module level for convenience
from .orchestrator import Orchestrator

__all__.extend(["Orchestrator"])