"""
Catalog Scout Agent - LangGraph ReAct agent for OpenMetadata catalog discovery.

This agent uses the prebuilt ReAct pattern for reasoning and tool execution.
All tools are discovered dynamically from the MCP server using native langchain-mcp-adapters.
"""

import logging
from typing import Any, Dict
from datetime import timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain.agents import create_agent

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection


class CatalogScout:
    """Catalog Scout Agent using LangGraph ReAct pattern with native MCP integration."""

    logger = logging.getLogger(__name__)

    SYSTEM_PROMPT = """You are the Catalog Scout, an expert at discovering and exploring the OpenMetadata data catalog.

You have access to all OpenMetadata MCP tools. You can search for tables, dashboards, pipelines, databases, and other entities. You can also get entity details, lineage information, and perform semantic search.

Key capabilities:
- search_metadata: Keyword-based search for specific entity types, names, owners, tags
- semantic_search: Meaning-based search when you don't know exact names  
- get_entity_details: Get full details for a specific entity by its fully qualified name
- get_entity_lineage: See upstream/downstream dependencies
- create_lineage: Link two assets together

Choose the appropriate tool based on the user's task. Use search_metadata for exact lookups, semantic_search for exploratory queries.

IMPORTANT: When using get_entity_details, use the fullyQualifiedName from search results directly - don't construct it manually.
"""

    def __init__(self):
        """Initialize the Catalog Scout ReAct agent with native MCP tools."""
        from ..config import get_settings
        settings = get_settings()
        self.llm = settings.create_llm_client(temperature=0.1, max_tokens=500)
        self.settings = settings

        # MCP client will be initialized lazily
        self._mcp_client: MultiServerMCPClient | None = None
        # Agent will be loaded dynamically when first executed
        self._agent = None

    @property
    def agent_id(self) -> str:
        return "catalog_scout"

    @property
    def display_name(self) -> str:
        return "Catalog Scout"

    @property
    def description(self) -> str:
        return "Discovers and explores entities in the OpenMetadata catalog"

    @property
    def avatar_emoji(self) -> str:
        return "🔍"

    @property
    def capabilities(self) -> list:
        return [
            {
                "name": "search_metadata",
                "description": "Keyword search for tables, dashboards, pipelines, and other entities"
            },
            {
                "name": "semantic_search",
                "description": "Meaning-based search for exploratory queries"
            },
            {
                "name": "get_entity_details",
                "description": "Get full details for a specific entity"
            },
            {
                "name": "get_entity_lineage",
                "description": "View upstream/downstream dependencies"
            },
            {
                "name": "create_lineage",
                "description": "Link two assets together"
            },
            {
                "name": "root_cause_analysis",
                "description": "Trace upstream failures via lineage"
            }
        ]

    def _get_mcp_client(self) -> MultiServerMCPClient:
        """Get or create the native MCP client using langchain-mcp-adapters."""
        if self._mcp_client is None:
            self._mcp_client = MultiServerMCPClient(
                connections={
                    "openmetadata": StreamableHttpConnection(
                        url=self.settings.openmetadata_mcp_url,
                        headers={"Authorization": f"Bearer {self.settings.openmetadata_jwt_token}"},
                        transport="streamable_http",
                        timeout=timedelta(seconds=30),
                        sse_read_timeout=timedelta(seconds=30),
                    )
                }
            )
        return self._mcp_client

    async def _get_agent(self):
        """Get or create the ReAct agent with native MCP tools."""
        if self._agent is None:
            mcp_client = self._get_mcp_client()
            tools = await mcp_client.get_tools()
            self.logger.info(f"[CatalogScout] Loaded {len(tools)} MCP tools")
            self._agent = create_agent(self.llm, tools, system_prompt=self.SYSTEM_PROMPT, debug=False)
        return self._agent

    async def execute(
        self,
        task: str,
        inputs: Dict[str, Any],
        mcp_client: Any = None
    ) -> str:
        """
        Execute the catalog scout agent on a task.

        Returns:
            A string response with the results
        """
        self.logger.info(f"[CatalogScout] Executing task: {task}")

        try:
            agent = await self._get_agent()

            # Build input for the agent
            from langchain_core.messages import HumanMessage
            input_data = {"messages": [{"role": "user", "content": task}]}

            # Run the agent and stream updates
            result_messages = []
            self.logger.info("[CatalogScout] Starting astream...")
            async for chunk in agent.astream(input_data, stream_mode="messages"):
                result_messages.append(chunk)

            self.logger.info(f"[CatalogScout] Streaming complete, {len(result_messages)} chunks received")

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
                        # Handle list content (e.g., from tool calls)
                        for item in content:
                            if isinstance(item, str):
                                full_response += item
                            elif isinstance(item, dict) and 'text' in item:
                                full_response += item['text']
            
            self.logger.info(f"[CatalogScout] Full response length: {len(full_response)}")
            return full_response if full_response else None

        except Exception as e:
            self.logger.error(f"[CatalogScout] Execution failed: {e}", exc_info=True)
            return f"Error: {str(e)}"


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(CatalogScout())
from .registry import AgentRegistry
AgentRegistry().register(CatalogScout())