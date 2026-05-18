"""
Shared MCP client utility using native langchain-mcp-adapters.

This module provides a singleton MCP client that connects to the OpenMetadata
MCP server using the official langchain-mcp-adapters library.
"""

import logging
from typing import List, Any
from datetime import timedelta

from langchain_core.tools import Tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from ..config import get_settings

logger = logging.getLogger(__name__)

# Singleton MCP client instance
_mcp_client: MultiServerMCPClient | None = None


def get_mcp_client() -> MultiServerMCPClient:
    """
    Get or create a singleton MCP client using native langchain-mcp-adapters.
    
    Returns:
        MultiServerMCPClient instance configured from settings
    """
    global _mcp_client
    
    if _mcp_client is None:
        settings = get_settings()
        _mcp_client = MultiServerMCPClient(
            connections={
                "openmetadata": StreamableHttpConnection(
                    url=settings.openmetadata_mcp_url,
                    headers={"Authorization": f"Bearer {settings.openmetadata_jwt_token}"},
                    transport="streamable_http",
                    timeout=timedelta(seconds=30),
                    sse_read_timeout=timedelta(seconds=30),
                )
            }
        )
        logger.info("Created native MCP client using langchain-mcp-adapters")
    
    return _mcp_client


async def get_mcp_tools_async() -> List[Tool]:
    """
    Get all tools from the MCP server as LangChain Tool objects (async).
    
    Returns:
        List of LangChain Tool objects from the MCP server
    """
    client = get_mcp_client()
    return await client.get_tools()


def get_mcp_tools() -> List[Tool]:
    """
    Get all tools from the MCP server as LangChain Tool objects (sync wrapper).
    
    Note: This uses asyncio.run() for synchronous contexts. In async contexts,
    prefer using get_mcp_tools_async() instead.
    
    Returns:
        List of LangChain Tool objects from the MCP server
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(get_mcp_tools_async())


def reset_mcp_client() -> None:
    """Reset the singleton MCP client (useful for testing)."""
    global _mcp_client
    _mcp_client = None
    logger.info("Reset MCP client singleton")