"""
Quality Guardian Agent - LangGraph Agent for Data Quality Analysis.

This module provides an agent that uses LangGraph's create_agent
framework with native MCP tools from langchain-mcp-adapters.
"""

import logging
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent

from ..config import get_settings
from ..mcp.native_client import get_mcp_tools_async

logger = logging.getLogger(__name__)


# =============================================================================
# QUALITY GUARDIAN AGENT CLASS
# =============================================================================

class QualityGuardian:
    """Quality Guardian Agent using LangGraph with native MCP tools."""

    SYSTEM_PROMPT = """You are the Quality Guardian, an expert at data quality analysis and validation.

You have access to OpenMetadata MCP tools for:
- Getting entity details (columns, descriptions, metadata)
- Getting table profiles (row counts, statistics)
- Performing root cause analysis
- Detecting anomalies in data

Key responsibilities:
1. **Table Profiling**: Get statistical profiles of tables (row counts, column stats)
2. **Anomaly Detection**: Identify unusual patterns, missing documentation, potential PII
3. **Quality Assessment**: Calculate overall quality scores and SLA compliance
4. **Root Cause Analysis**: Trace upstream issues when data quality problems occur

Use the MCP tools to gather information and provide quality assessments. Analyze columns for:
- Missing descriptions
- Potential PII (columns named 'ssn', 'password', 'credit_card', etc.)
- Data type inconsistencies
- Missing constraints or keys

Provide actionable recommendations for improving data quality.
"""

    @property
    def agent_id(self) -> str:
        return "quality_guardian"

    @property
    def display_name(self) -> str:
        return "Quality Guardian"

    @property
    def description(self) -> str:
        return "Analyzes data quality, detects anomalies, and validates SLAs"

    @property
    def avatar_emoji(self) -> str:
        return "⚖️"

    @property
    def capabilities(self) -> list:
        return [
            {
                "name": "table_profiling",
                "description": "Profiles tables with statistical metrics"
            },
            {
                "name": "anomaly_detection",
                "description": "Detects anomalies in data distribution"
            },
            {
                "name": "quality_assessment",
                "description": "Assesses overall data quality score"
            }
        ]

    def __init__(self):
        """Initialize the Quality Guardian agent with native MCP tools."""
        settings = get_settings()
        self.llm = settings.create_llm_client(temperature=0.1, max_tokens=500)

        # Agent loaded lazily on first execute
        self._agent = None

    async def _get_agent(self):
        """Get or create the agent with native MCP tools."""
        if self._agent is None:
            tools = await get_mcp_tools_async()
            logger.info(f"[QualityGuardian] Loaded {len(tools)} MCP tools")
            self._agent = create_agent(self.llm, tools, system_prompt=self.SYSTEM_PROMPT, debug=False)
        return self._agent

    async def execute(
        self,
        task: str,
        inputs: Dict[str, Any],
        mcp_client: Any = None
    ) -> str:
        """
        Execute the quality guardian agent on a task.
        
        Returns:
            A string response with the results
        """
        logger.info(f"[QualityGuardian] Executing task: {task}")
        
        try:
            agent = await self._get_agent()
            
            input_data = {"messages": [{"role": "user", "content": task}]}
            
            result_messages = []
            async for chunk in agent.astream(input_data, stream_mode="messages"):
                result_messages.append(chunk)

            # Accumulate content from all AIMessage chunks
            full_response = ""
            for chunk in result_messages:
                if isinstance(chunk, tuple):
                    msg = chunk[0]
                else:
                    msg = chunk
                
                if hasattr(msg, 'content'):
                    content = msg.content
                    if isinstance(content, str):
                        full_response += content
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, str):
                                full_response += item
                            elif isinstance(item, dict) and 'text' in item:
                                full_response += item['text']
            
            return full_response if full_response else None
            
        except Exception as e:
            logger.error(f"[QualityGuardian] Execution failed: {e}", exc_info=True)
            return f"Error: {str(e)}"


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(QualityGuardian())