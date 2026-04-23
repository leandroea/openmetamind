"""
MCP (Metadata Control Plane) module for OpenMetaMind.
"""

from .client import OpenMetadataMCPClient, get_mcp_client

__all__ = [
    "OpenMetadataMCPClient",
    "get_mcp_client",
]