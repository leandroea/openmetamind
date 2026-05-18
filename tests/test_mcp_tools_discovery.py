"""
Discover available MCP tools from OpenMetadata MCP Server.

Uses the MCP Protocol 'tools/list' request to get all available tools.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List

import httpx

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


async def discover_tools(base_url: str, jwt_token: str) -> List[Dict[str, Any]]:
    """
    Discover all available tools from the MCP server using tools/list.
    
    Args:
        base_url: The MCP server endpoint URL
        jwt_token: JWT token for authentication
        
    Returns:
        List of tool definitions
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        request_id = 1
        
        # Build JSON-RPC request for tools/list
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {jwt_token}"
        }
        
        logger.info(f"Sending tools/list request to {base_url}")
        
        response = await client.post(base_url, headers=headers, json=payload)
        response.raise_for_status()
        
        result_data = response.json()
        logger.info(f"Raw response: {json.dumps(result_data, indent=2)}")
        
        # Extract tools from response
        if "error" in result_data:
            raise ValueError(f"MCP server returned error: {result_data['error']}")
        
        result = result_data.get("result", {})
        tools = result.get("tools", [])
        
        return tools


def format_tool_info(tools: List[Dict[str, Any]]) -> str:
    """Format tool information for display."""
    output = []
    output.append(f"\n{'='*70}")
    output.append(f"Found {len(tools)} tools on OpenMetadata MCP Server")
    output.append(f"{'='*70}\n")
    
    for i, tool in enumerate(tools, 1):
        name = tool.get("name", "unknown")
        description = tool.get("description", "No description")
        input_schema = tool.get("inputSchema", {})
        
        output.append(f"{i}. **{name}**")
        output.append(f"   Description: {description}")
        
        # Format input schema
        if input_schema:
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            if properties:
                output.append("   Parameters:")
                for prop_name, prop_info in properties.items():
                    prop_type = prop_info.get("type", "any")
                    required_marker = " (required)" if prop_name in required else " (optional)"
                    default = prop_info.get("default")
                    desc = prop_info.get("description", "")
                    
                    default_str = f" [default: {default}]" if default is not None else ""
                    desc_str = f" - {desc}" if desc else ""
                    
                    output.append(f"     - {prop_name}: {prop_type}{required_marker}{default_str}{desc_str}")
        
        output.append("")
    
    return "\n".join(output)


async def main():
    """Main entry point."""
    # Load from .env or settings
    try:
        from src.config import get_settings
        settings = get_settings()
        base_url = settings.openmetadata_mcp_url
        jwt_token = settings.openmetadata_jwt_token
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.info("Please ensure OPENMETADATA_MCP_URL and OPENMETADATA_JWT_TOKEN are set in .env")
        sys.exit(1)
    
    logger.info(f"Connecting to MCP server at {base_url}")
    
    try:
        tools = await discover_tools(base_url, jwt_token)
        output = format_tool_info(tools)
        print(output)
        
        # Also save to file for reference
        output_file = "mcp_tools_discovered.json"
        with open(output_file, "w") as f:
            json.dump({"tools": tools}, f, indent=2)
        logger.info(f"Full tool definitions saved to {output_file}")
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error discovering tools: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())