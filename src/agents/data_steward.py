"""
Data Steward Agent - LangGraph Prebuilt ReAct Agent for Data Governance.

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
# DATA STEWARD AGENT CLASS
# =============================================================================

class DataSteward:
    """Data Steward Agent using LangGraph agent with native MCP tools."""

    SYSTEM_PROMPT = """You are the Data Steward, an expert at data governance and classification.

You have access to OpenMetadata MCP tools for:
- Getting entity details (columns, descriptions, tags)
- Adding tags to entities
- Adding owners to entities

Key responsibilities:
1. **PII Detection**: Analyze column names and data types to identify potential PII (email, phone, SSN, credit card, etc.)
2. **Tag Assignment**: Suggest and apply governance tags based on data content and sensitivity
3. **Ownership Management**: Suggest or assign data owners

Use the MCP tools to gather information and make recommendations. When analyzing for PII, look at column names like 'email', 'phone', 'ssn', 'credit_card', 'password', etc.

Be thorough in your analysis - check all columns for potential issues.
"""

    @property
    def agent_id(self) -> str:
        return "data_steward"

    @property
    def display_name(self) -> str:
        return "Data Steward"

    @property
    def description(self) -> str:
        return "Handles data classification, PII detection, tag assignment, and ownership management"

    @property
    def avatar_emoji(self) -> str:
        return "🛡️"

    @property
    def capabilities(self) -> list:
        return [
            {
                "name": "pii_detection",
                "description": "Detects personally identifiable information in columns"
            },
            {
                "name": "tag_assignment",
                "description": "Assigns governance tags to entities"
            },
            {
                "name": "ownership_management",
                "description": "Suggests or assigns asset owners"
            }
        ]

    def __init__(self):
        """Initialize the Data Steward agent with native MCP tools."""
        settings = get_settings()
        self.llm = settings.create_llm_client(temperature=0.1, max_tokens=500)
        
        # Agent loaded lazily on first execute
        self._agent = None

    async def _get_agent(self):
        """Get or create the agent with native MCP tools."""
        if self._agent is None:
            tools = await get_mcp_tools_async()
            logger.info(f"[DataSteward] Loaded {len(tools)} MCP tools")
            self._agent = create_agent(self.llm, tools, system_prompt=self.SYSTEM_PROMPT, debug=False)
        return self._agent

    async def execute(
        self,
        task: str,
        inputs: Dict[str, Any],
        mcp_client: Any = None
    ) -> str:
        """
        Execute the data steward agent on a task.
        
        Returns:
            A string response with the results
        """
        logger.info(f"[DataSteward] Executing task: {task}")
        
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
                    # Content can be str or list
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
            logger.error(f"[DataSteward] Execution failed: {e}", exc_info=True)
            return f"Error: {str(e)}"


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(DataSteward())