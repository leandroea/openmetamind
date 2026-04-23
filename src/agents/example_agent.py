"""
Example agent demonstrating the SwarmAgent interface.
This is a placeholder showing how to implement a real agent.
"""

import asyncio
from typing import Dict, Any

from .base import SwarmAgent, Capability
from ..models.state import AgentFinding, MCPToolCall
from .registry import AgentRegistry


class ExampleAgent(SwarmAgent):
    """An example agent that demonstrates the SwarmAgent interface."""
    
    agent_id = "example_agent"
    display_name = "Example Agent"
    description = "An example agent showing how to implement the SwarmAgent interface"
    avatar_emoji = "🤖"
    
    capabilities = [
        Capability(
            name="example_task",
            description="Performs an example task",
            input_schema={"task_description": "string"},
            output_schema={"result": "string"}
        )
    ]
    
    async def can_handle(self, task_description: str) -> float:
        """
        Simple keyword matching for demonstration.
        Returns high confidence if task contains example keywords.
        """
        task_lower = task_description.lower()
        if any(keyword in task_lower for keyword in ["example", "demo", "sample"]):
            return 0.9
        return 0.1
    
    async def execute(
        self, 
        task: str, 
        inputs: Dict[str, Any], 
        mcp_client: Any
    ) -> AgentFinding:
        """
        Execute the example agent's logic.
        
        In a real implementation, this would:
        1. Use the mcp_client to gather data from OpenMetadata
        2. Use an LLM to analyze the data
        3. Return structured findings
        
        For now, we return a placeholder finding.
        """
        # Simulate some work
        await asyncio.sleep(0.1)
        
        # Create a placeholder finding
        finding = AgentFinding(
            agent_id=self.agent_id,
            subtask_id="example_subtask",
            task_description=task,
            finding_type="other",
            summary="Example agent completed successfully",
            details={
                "task": task,
                "inputs_received": list(inputs.keys()),
                "message": "This is a placeholder finding from the example agent"
            },
            confidence=0.95,
            proposed_actions=[],  # No actions in this example
            mcp_tool_calls=[],    # No MCP calls in this example
            llm_reasoning="The example agent performed a simple task and returned this finding."
        )
        
        return finding


# Self-register on import
AgentRegistry().register(ExampleAgent())