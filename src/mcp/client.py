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


def get_mcp_client() -> "OpenMetadataMCPClient":
    """
    Dependency injection helper to get an MCP client instance.
    
    Reads configuration from settings (which loads from .env).
    
    Returns:
        OpenMetadataMCPClient instance configured from settings
        
    Note:
        This function does not handle the async context manager lifecycle.
        For proper resource management, use the client as an async context manager:
        async with get_mcp_client() as client:
            # use client
    """
    from ..config import get_settings
    settings = get_settings()
    return OpenMetadataMCPClient(
        base_url=settings.openmetadata_mcp_url,
        jwt_token=settings.openmetadata_jwt_token
    )


class OpenMetadataMCPClient:
    """
    Async client for OpenMetadata MCP server.

    Uses JSON-RPC 2.0 over HTTP with JWT Bearer authentication.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        jwt_token: Optional[str] = None
    ):
        """
        Initialize the MCP client.

        Args:
            base_url: The MCP endpoint URL. If not provided, reads from settings.
            jwt_token: JWT token for authentication. If not provided, reads from settings.
        """
        # Load from settings if not provided
        if base_url is None or jwt_token is None:
            from ..config import get_settings
            settings = get_settings()
            base_url = base_url or settings.openmetadata_mcp_url
            jwt_token = jwt_token or settings.openmetadata_jwt_token
        
        self.base_url = base_url
        self.jwt_token = jwt_token
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
            "Accept": "application/json",
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
            
            # Handle nested response format: result.content[0].text contains JSON string
            # This is how OpenMetadata MCP server formats responses
            raw_result = result_data.get("result", {})
            if isinstance(raw_result, dict) and "content" in raw_result:
                content = raw_result["content"]
                if isinstance(content, list) and len(content) > 0:
                    first_item = content[0]
                    if isinstance(first_item, dict) and "text" in first_item:
                        # Parse the JSON string inside the text field
                        text_content = first_item["text"]
                        try:
                            parsed = json.loads(text_content)
                            # Check if it's an error response embedded in text
                            if isinstance(parsed, dict) and "statusCode" in parsed:
                                error_msg = parsed.get("error", parsed.get("message", "Unknown error"))
                                raise ValueError(f"MCP tool {tool_name} returned error: {error_msg}")
                            return parsed
                        except json.JSONDecodeError:
                            # If it's not JSON, return the raw text
                            return {"text": text_content}
            
            # Return the result directly if not in nested format
            return raw_result if raw_result else {}
            
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

    # MCP Tool Methods - Using actual OpenMetadata MCP server tool names
    
    async def search_metadata(
        self, 
        query: str,
        entity_type: Optional[str] = None,
        size: int = 10
    ) -> Dict[str, Any]:
        """
        Keyword-based search for data assets in OpenMetadata.
        
        Args:
            query: Natural language search query
            entity_type: Filter by entity type (e.g., 'table', 'dashboard')
            size: Number of results to return
            
        Returns:
            Search results with entities
        """
        arguments = {"query": query, "size": size}
        if entity_type:
            arguments["entityType"] = entity_type
            
        return await self._call_mcp_tool("search_metadata", arguments)

    async def search_metadata_all(
        self,
        query: str,
        entity_type: Optional[str] = None,
        max_results: int = 1000
    ) -> Dict[str, Any]:
        """
        Search for data assets and return ALL results with pagination.
        
        Args:
            query: Natural language search query
            entity_type: Filter by entity type (e.g., 'table', 'dashboard')
            max_results: Maximum number of results to fetch (default 1000)
            
        Returns:
            Search results with all entities found, plus pagination info
        """
        all_entities = []
        current_offset = 0
        page_size = 50  # Fetch 50 at a time
        
        while len(all_entities) < max_results:
            arguments = {"query": query, "size": page_size, "from": current_offset}
            if entity_type:
                arguments["entityType"] = entity_type
            
            result = await self._call_mcp_tool("search_metadata", arguments)
            
            entities = result.get("results", [])
            all_entities.extend(entities)
            
            # Check if there are more results
            has_more = result.get("hasMore", False)
            total_found = result.get("totalFound", 0)
            
            # If we've fetched everything or reached max_results, stop
            if not has_more or len(all_entities) >= total_found:
                break
                
            # Continue to next page
            current_offset += page_size
        
        return {
            "results": all_entities[:max_results],
            "totalFound": len(all_entities),
            "hasMore": len(all_entities) < total_found,
            "returnedCount": len(all_entities)
        }

    async def semantic_search(
        self, 
        query: str,
        size: int = 10
    ) -> Dict[str, Any]:
        """
        Meaning-based discovery using vector embeddings.
        
        Args:
            query: Natural language query describing what you're looking for
            size: Number of results to return
            
        Returns:
            Semantic search results
        """
        return await self._call_mcp_tool("semantic_search", {"query": query, "size": size})

    async def get_entity_details(
        self,
        entity_type: str,
        fqn: str
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific entity.
        
        Args:
            entity_type: Type of entity (e.g., 'table', 'dashboard')
            fqn: Fully qualified name of the entity
            
        Returns:
            Entity details
        """
        return await self._call_mcp_tool("get_entity_details", {
            "entityType": entity_type,
            "fqn": fqn
        })

    async def patch_entity(
        self,
        entity_type: str,
        fqn: str,
        patch: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Patch an entity using JSONPatch operations.
        
        Args:
            entity_type: Type of entity to patch
            fqn: Fully qualified name of the entity
            patch: JSONPatch operations
            
        Returns:
            Patched entity result
        """
        logger.debug(f"patch_entity called: entity_type={entity_type}, fqn={fqn}, patch={json.dumps(patch)}")
        return await self._call_mcp_tool("patch_entity", {
            "entityType": entity_type,
            "fqn": fqn,
            "patch": json.dumps(patch)
        })

    async def get_entity_lineage(
        self,
        entity_type: str,
        fqn: str,
        upstream_depth: int = 3,
        downstream_depth: int = 3
    ) -> Dict[str, Any]:
        """
        Get lineage information for an entity.
        
        Args:
            entity_type: Type of entity
            fqn: Fully qualified name of the entity
            upstream_depth: Number of upstream hops
            downstream_depth: Number of downstream hops
            
        Returns:
            Lineage information
        """
        return await self._call_mcp_tool("get_entity_lineage", {
            "entityType": entity_type,
            "fqn": fqn,
            "upstreamDepth": upstream_depth,
            "downstreamDepth": downstream_depth
        })

    async def create_glossary(
        self,
        name: str,
        description: str,
        mutually_exclusive: bool = False,
        owners: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new glossary.
        
        Args:
            name: Name of the glossary
            description: Description
            mutually_exclusive: Whether terms are mutually exclusive
            owners: List of owners
            
        Returns:
            Created glossary result
        """
        arguments = {
            "name": name,
            "description": description,
            "mutuallyExclusive": mutually_exclusive
        }
        if owners:
            arguments["owners"] = owners
            
        return await self._call_mcp_tool("create_glossary", arguments)

    async def create_glossary_term(
        self,
        glossary: str,
        name: str,
        description: str,
        parent_term: Optional[str] = None,
        owners: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new glossary term.
        
        Args:
            glossary: Glossary name
            name: Term name
            description: Term description
            parent_term: Optional parent term
            owners: List of owners
            
        Returns:
            Created term result
        """
        arguments = {
            "glossary": glossary,
            "name": name,
            "description": description
        }
        if parent_term:
            arguments["parentTerm"] = parent_term
        if owners:
            arguments["owners"] = owners
            
        return await self._call_mcp_tool("create_glossary_term", arguments)

    async def create_test_case(
        self,
        name: str,
        fqn: str,
        test_definition_name: str,
        parameter_values: List[Dict[str, str]],
        entity_type: str = "table",
        column_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a test case for a table or column.
        
        Args:
            name: Name of the test case
            fqn: Fully qualified name of the table
            test_definition_name: Fully qualified name of the test definition
            parameter_values: Parameter values for the test
            entity_type: Type of entity (default: 'table')
            column_name: Column name for column-level tests
            description: Test case description
            
        Returns:
            Created test case result
        """
        arguments = {
            "name": name,
            "fqn": fqn,
            "testDefinitionName": test_definition_name,
            "parameterValues": parameter_values,
            "entityType": entity_type
        }
        if column_name:
            arguments["columnName"] = column_name
        if description:
            arguments["description"] = description
            
        return await self._call_mcp_tool("create_test_case", arguments)

    async def get_test_definitions(
        self,
        entity_type: str = "TABLE",
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get all test definitions.
        
        Args:
            entity_type: Entity type ('TABLE' or 'COLUMN')
            limit: Maximum number of results
            
        Returns:
            Test definitions
        """
        return await self._call_mcp_tool("get_test_definitions", {
            "entityType": entity_type,
            "limit": limit
        })

    async def create_lineage(
        self,
        source_entity_type: str,
        source_fqn: str,
        target_entity_type: str,
        target_fqn: str
    ) -> Dict[str, Any]:
        """
        Create a lineage relationship between two entities.
        
        Args:
            source_entity_type: Type of source entity (e.g., 'table', 'pipeline')
            source_fqn: Fully qualified name of the source entity
            target_entity_type: Type of target entity
            target_fqn: Fully qualified name of the target entity
            
        Returns:
            Created lineage result
        """
        return await self._call_mcp_tool("create_lineage", {
            "sourceEntityType": source_entity_type,
            "sourceFQN": source_fqn,
            "targetEntityType": target_entity_type,
            "targetFQN": target_fqn
        })

    async def root_cause_analysis(
        self,
        fqn: str,
        entity_type: str,
        upstream_depth: int = 3,
        downstream_depth: int = 3
    ) -> Dict[str, Any]:
        """
        Perform root cause analysis via data quality lineage.
        
        Args:
            fqn: Fully qualified name of the entity
            entity_type: Type of entity
            upstream_depth: Upstream hops
            downstream_depth: Downstream hops
            
        Returns:
            Root cause analysis results
        """
        return await self._call_mcp_tool("root_cause_analysis", {
            "fqn": fqn,
            "entityType": entity_type,
            "upstreamDepth": upstream_depth,
            "downstreamDepth": downstream_depth
        })

    async def get_table_profile(
        self,
        fqn: str
    ) -> Dict[str, Any]:
        """
        Get profile/statistics for a table.
        
        Args:
            fqn: Fully qualified name of the table
            
        Returns:
            Table profile data including row count, size, etc.
        """
        return await self._call_mcp_tool("get_table_profile", {
            "fqn": fqn
        })

    @staticmethod
    def build_description_patch(description: str) -> List[Dict[str, Any]]:
        """
        Build a JSON Patch payload for updating entity descriptions.
        
        This is an INTERNAL helper - not exposed as an MCP tool.
        All description updates must go through patch_entity.
        
        Args:
            description: The new description text
            
        Returns:
            JSON Patch payload list with replace operation
        """
        return [{"op": "replace", "path": "/description", "value": description}]

    async def add_tags(
        self,
        fqn: str,
        entity_type: str,
        tags: List[str]
    ) -> Dict[str, Any]:
        """
        Add tags to an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            entity_type: Type of entity (e.g., 'table', 'column')
            tags: List of tag names to add
            
        Returns:
            Result of the tag operation
        """
        # Tags are typically stored at /tags path
        patch = [{"op": "add", "path": "/tags", "value": tags}]
        return await self.patch_entity(entity_type, fqn, patch)

    async def update_description(
        self,
        fqn: str,
        entity_type: str,
        description: str
    ) -> Dict[str, Any]:
        """
        Update the description of an entity using patch_entity.
        
        Args:
            fqn: Fully qualified name of the entity
            entity_type: Type of entity (e.g., 'table', 'column')
            description: New description text
            
        Returns:
            Result of the update operation
        """
        # Check if description already exists to determine correct JSON Patch operation
        # Use "add" if field doesn't exist, "replace" if it does (RFC 6902 compliant)
        try:
            entity_details = await self.get_entity_details(entity_type, fqn)
            has_description = entity_details.get("description") is not None
        except Exception:
            # If we can't fetch details, assume field doesn't exist and use "add"
            has_description = False
        
        op = "replace" if has_description else "add"
        patch = [
            {"op": op, "path": "/description", "value": description}
        ]
        return await self.patch_entity(entity_type, fqn, patch)

    async def add_owner(
        self,
        fqn: str,
        entity_type: str,
        owner: str,
        owner_type: str = "user"
    ) -> Dict[str, Any]:
        """
        Add an owner to an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            entity_type: Type of entity (e.g., 'table')
            owner: Owner identifier (username or team name)
            owner_type: Type of owner ('user' or 'team')
            
        Returns:
            Result of the owner operation
        """
        # Owner is typically stored at /owner path
        owner_obj = {"type": owner_type, "id": owner}
        patch = [{"op": "add", "path": "/owner", "value": owner_obj}]
        return await self.patch_entity(entity_type, fqn, patch)

    async def remove_owner(
        self,
        fqn: str,
        entity_type: str,
        owner: str
    ) -> Dict[str, Any]:
        """
        Remove an owner from an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            entity_type: Type of entity (e.g., 'table')
            owner: Owner identifier to remove
            
        Returns:
            Result of the owner removal operation
        """
        # Remove owner by replacing with null or removing the path
        patch = [{"op": "remove", "path": "/owner"}]
        return await self.patch_entity(entity_type, fqn, patch)

    async def delete_tag(
        self,
        fqn: str,
        entity_type: str,
        tag: str
    ) -> Dict[str, Any]:
        """
        Delete a tag from an entity.
        
        Args:
            fqn: Fully qualified name of the entity
            entity_type: Type of entity (e.g., 'table', 'column')
            tag: Tag name to delete
            
        Returns:
            Result of the tag deletion operation
        """
        # Note: Removing a specific tag from an array requires knowing the exact path
        # This is a simplified implementation - in practice, you may need to
        # first get the entity, find the tag index, then remove by path
        patch = [{"op": "replace", "path": "/tags", "value": []}]  # Simplified - clears all tags
        return await self.patch_entity(entity_type, fqn, patch)