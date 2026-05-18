"""
Documentation Agent - LangGraph Agent for documenting OpenMetadata entities.

This agent uses LangGraph's create_agent with native MCP tools from langchain-mcp-adapters.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent

from ..config import get_settings
from ..mcp.native_client import get_mcp_tools_async

logger = logging.getLogger(__name__)


class DocumentationAgent:
    """Documentation Agent using LangGraph with native MCP tools."""

    SYSTEM_PROMPT = """You are a data documentation expert, skilled at finding undocumented entities and generating meaningful descriptions.

You have access to OpenMetadata MCP tools for:
- Searching for entities (tables, dashboards, pipelines)
- Getting entity details (columns, descriptions, metadata)
- Adding descriptions to entities
- Finding undocumented entities

Key capabilities:
1. **Find Undocumented**: Search for tables/entities that lack descriptions
2. **Generate Descriptions**: Create business-friendly descriptions based on entity metadata
3. **Document Entities**: Add or update descriptions for entities

When documenting an entity:
- Look at the table name, columns, and tags to understand its purpose
- Generate a ONE-sentence business description that explains what data it contains
- Consider the database and schema context
- Flag any columns that lack descriptions

Be thorough - check all columns and provide actionable recommendations.
"""

    @property
    def agent_id(self) -> str:
        return "documentation_agent"

    @property
    def display_name(self) -> str:
        return "Documentation Agent"

    @property
    def description(self) -> str:
        return "Finds undocumented entities and generates business-friendly descriptions"

    @property
    def avatar_emoji(self) -> str:
        return "📝"

    @property
    def capabilities(self) -> list:
        return [
            {
                "name": "find_undocumented",
                "description": "Finds tables and columns missing descriptions"
            },
            {
                "name": "generate_description",
                "description": "Generates business-friendly descriptions via LLM"
            },
            {
                "name": "document_entities",
                "description": "Full pipeline to document undocumented entities"
            }
        ]

    def __init__(self):
        """Initialize the Documentation Agent with native MCP tools."""
        settings = get_settings()
        self.llm = settings.create_llm_client(temperature=0.3, max_tokens=500)

        # Agent loaded lazily on first execute
        self._agent = None

    async def _get_agent(self):
        """Get or create the agent with native MCP tools."""
        if self._agent is None:
            tools = await get_mcp_tools_async()
            logger.info(f"[DocumentationAgent] Loaded {len(tools)} MCP tools")
            self._agent = create_agent(self.llm, tools, system_prompt=self.SYSTEM_PROMPT, debug=False)
        return self._agent

    async def execute(
        self, 
        task: str, 
        inputs: Dict[str, Any], 
        mcp_client: Any = None
    ) -> str:
        """
        Execute the documentation agent on a task.
        
        Returns:
            A string response with the results
        """
        logger.info(f"[DocumentationAgent] Executing task: {task}")
        
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
            logger.error(f"[DocumentationAgent] Execution failed: {e}", exc_info=True)
            return f"Error: {str(e)}"


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(DocumentationAgent())
