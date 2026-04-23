"""
Async MCP client for OpenMetadata.

Implements JSON-RPC 2.0 over HTTP with JWT Bearer authentication.
"""

import os
import time
import json
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .models import Entity, TableProfile, ColumnProfile, UsageStats

logger = logging.getLogger(__name__)


class OpenMetadataMCPClient:
    """
    Async client for OpenMetadata MCP server.
    
    Uses JSON-RPC 2.0 over HTTP with JWT Bearer authentication.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8585/mcp",
        jwt_token: Optional[str] = None
    ):
        """
        Initialize the MCP client.
        
        Args:
            base_url: The MCP endpoint URL (default: http://localhost:8585/mcp)
            jwt_token: JWT token for authentication. If not provided, 
                      reads from OPENMETADATA_JWT_TOKEN environment variable.
        """
        self.base_url = base_url
        self.jwt_token = jwt_token or os.getenv("OPENMETADATA_JWT_TOKEN")
        if not self.jwt_token:
            raise ValueError(
                "JWT token must be provided either as argument or via OPENMETADATA_JWT_TOKEN environment variable"
            )
        
        self._client: Optional[httpx.AsyncClient] = None
        self._request_id = 0

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    def _get_next_id(self) -> int:
        """Generate a unique request ID for JSON-RPC."""
        self._request_id += 1
        return self._request_id

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers for MCP requests."""
        return {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json",
        }

    def _build_json_rpc_payload(
        self, 
        method: str, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build JSON-RPC 2.0 payload."""
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._get_next_id(),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True
    )
    async def _call_mcp_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make a JSON-RPC call to the MCP server.
        
        Args:
            tool_name: Name of the MCP tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            The result field from the JSON-RPC response
            
        Raises:
            httpx.HTTPStatusError: If the HTTP request returns an error status
            httpx.RequestError: If there's a connection or timeout error (after retries)
            ValueError: If the JSON-RPC response contains an error
        """
        if not self._client:
            raise RuntimeError("MCP client not initialized. Use async context manager or call __aenter__.")
        
        payload = self._build_json_rpc_payload(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments
            }
        )
        
        start_time = time.time()
        try:
            response = await self._client.post(
                self.base_url,
                headers=self._build_headers(),
                json=payload
            )
            response.raise_for_status()
            
            latency = time.time() - start_time
            result_data = response.json()
            
            # Log the call
            logger.info(
                "MCP tool call",
                extra={
                    "tool": tool_name,
                    "params": arguments,
                    "latency": latency,
                    "request_id": payload["id"]
                }
            )
            
            # Check for JSON-RPC error
            if "error" in result_data:
                error_msg = result_data["error"].get("message", "Unknown error")
                raise ValueError(f"MCP tool {tool_name} returned error: {error_msg}")
            
            # Return the result
            return result_data.get("result", {})
            
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling MCP tool {tool_name}: {e.response.status_code} - {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error calling MCP tool {tool_name}: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from MCP tool {tool_name}: {str(e)}")
            raise

    # MCP Tool Methods
    
    async def list_entities(
        self, 
        entity_type: str, 
        database: Optional[str] = None
    ) -> List[Entity]:
        """
        List entities of a given type from OpenMetadata.
        
        Args:
            entity_type: Type of entity (e.g., 'table', 'database')
            database: Optional database name to filter by
            
        Returns:
            List of Entity objects
        """
        arguments = {"entityType": entity_type}
        if database:
            arguments["database"] = database
            
        result = await self._call_mcp_tool("list_entities", arguments)
        # Assuming the result is a list of entities
        return [Entity(**entity) for entity in result.get("entities", [])]

    async def get_table_profile(self, fqn: str) -> TableProfile:
        """
        Get profile data for a table.
        
        Args:
            fqn: Fully qualified name of the table
            
        Returns:
            TableProfile object
        """
        result = await self._call_mcp_tool("get_table_profile", {"fqn": fqn})
        return TableProfile(**result)

    async def get_column_profile(self, fqn: str) -> ColumnProfile:
        """
        Get profile data for a column.
        
        Args:
            fqn: Fully qualified name of the column
            
        Returns:
            ColumnProfile object
        """
        result = await self._call_mcp_tool("get_column_profile", {"fqn": fqn})
        return ColumnProfile(**result)

    async def get_usage_stats(
        self, 
        fqn: str, 
        days: int = 30
    ) -> UsageStats:
        """
        Get usage statistics for an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            days: Number of days to look back (default: 30)
            
        Returns:
            UsageStats object
        """
        result = await self._call_mcp_tool("get_usage_stats", {"fqn": fqn, "days": days})
        return UsageStats(**result)

    async def add_tags(self, fqn: str, tags: List[str]) -> bool:
        """
        Add tags to an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            tags: List of tag names to add
            
        Returns:
            True if successful
        """
        result = await self._call_mcp_tool("add_tags", {"fqn": fqn, "tags": tags})
        return bool(result)

    async def update_owner(self, fqn: str, owner: str) -> bool:
        """
        Update the owner of an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            owner: New owner (user or team name)
            
        Returns:
            True if successful
        """
        result = await self._call_mcp_tool("update_owner", {"fqn": fqn, "owner": owner})
        return bool(result)

    async def update_description(self, fqn: str, description: str) -> bool:
        """
        Update the description of an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            description: New description
            
        Returns:
            True if successful
        """
        result = await self._call_mcp_tool("update_description", {"fqn": fqn, "description": description})
        return bool(result)


def get_mcp_client() -> OpenMetadataMCPClient:
    """
    Dependency injection helper to get an MCP client instance.
    
    Returns:
        OpenMetadataMCPClient instance configured from environment
        
    Note:
        This function does not handle the async context manager lifecycle.
        For proper resource management, use the client as an async context manager:
        async with OpenMetadataMCPClient() as client:
            # use client
    """
    return OpenMetadataMCPClient()