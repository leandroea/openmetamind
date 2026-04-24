#!/usr/bin/env python
"""
MCP Server Test Script

Tests connection to the OpenMetadata MCP server and lists available tools.
"""

import asyncio
import json
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration from environment
MCP_URL = os.getenv("OPENMETADATA_MCP_URL", "http://localhost:8585/mcp")
JWT_TOKEN = os.getenv("OPENMETADATA_JWT_TOKEN", "")


async def list_mcp_tools():
    """Send a JSON-RPC request to list all available MCP tools."""
    if not JWT_TOKEN:
        print("ERROR: OPENMETADATA_JWT_TOKEN is not set in environment variables")
        return
    
    print(f"Connecting to MCP server at: {MCP_URL}")
    print(f"JWT Token: {JWT_TOKEN[:20]}... (truncated)")
    print("-" * 50)
    
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # JSON-RPC request to list tools
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 1
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print("Sending tools/list request...")
            response = await client.post(MCP_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            print("\nFull Response:")
            print(json.dumps(result, indent=2))
            
            if "result" in result:
                tools = result["result"].get("tools", [])
                print(f"\n\nFound {len(tools)} tools:")
                for i, tool in enumerate(tools, 1):
                    print(f"\n{i}. {tool.get('name', 'unknown')}")
                    desc = tool.get('description', 'No description')
                    print(f"   Description: {desc}")
                    
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error: {e.response.status_code}")
            print(f"Response: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Request Error: {str(e)}")
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")


async def test_tool_call(tool_name: str, arguments: dict):
    """Test calling a specific MCP tool."""
    if not JWT_TOKEN:
        print("ERROR: OPENMETADATA_JWT_TOKEN is not set")
        return
    
    print(f"\nTesting tool: {tool_name}")
    print(f"Arguments: {json.dumps(arguments, indent=2)}")
    print("-" * 50)
    
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": 2
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(MCP_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            print("\nFull Response:")
            print(json.dumps(result, indent=2))
            
            return result
            
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error: {e.response.status_code}")
            print(f"Response: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Request Error: {str(e)}")
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")


async def main():
    print("=" * 60)
    print("OpenMetadata MCP Server Test")
    print("=" * 60)
    
    # First, list all available tools
    await list_mcp_tools()
    
    print("\n\n" + "=" * 60)
    print("Testing specific tools...")
    print("=" * 60)
    
    # Test search_metadata for all tables - "list all tables"
    await test_tool_call("search_metadata", {"query": "table", "entityType": "table", "size": 20})
    
    # Test search_metadata with empty query to get all tables
    await test_tool_call("search_metadata", {"entityType": "table", "size": 20})
    
    # Test get_entity_details with correct FQN
    await test_tool_call("get_entity_details", {"entityType": "table", "fqn": "sample_data.ecommerce_db.shopify.raw_customer"})
    
    # Test get_entity_lineage
    await test_tool_call("get_entity_lineage", {"entityType": "table", "fqn": "sample_data.ecommerce_db.shopify.raw_customer"})

    # Test semantic_search
    await test_tool_call("semantic_search", {"query": "customer orders", "size": 5})


if __name__ == "__main__":
    asyncio.run(main())