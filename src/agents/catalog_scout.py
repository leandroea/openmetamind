"""
Catalog Scout Agent - Discovers entities in OpenMetadata.
"""

import asyncio
import logging
from typing import Dict, Any, List

from .base import SwarmAgent, Capability
from ..models.state import AgentFinding
from ..mcp.client import get_mcp_client, OpenMetadataMCPClient

logger = logging.getLogger(__name__)


class CatalogScout(SwarmAgent):
    """Discovers entities (tables, databases, etc) in OpenMetadata."""
    
    agent_id = "catalog_scout"
    display_name = "Catalog Scout"
    description = "Discovers and lists entities in the OpenMetadata catalog"
    avatar_emoji = "🔍"
    
    capabilities = [
        Capability(
            name="list_entities",
            description="Lists entities of a given type from OpenMetadata",
            input_schema={"entity_type": "string", "database": "string"},
            output_schema={"entities": "list[Entity]", "count": "integer"}
        ),
        Capability(
            name="search_catalog",
            description="Searches for entities matching a query",
            input_schema={"query": "string", "entity_type": "string"},
            output_schema={"entities": "list[Entity]", "count": "integer"}
        ),
        Capability(
            name="get_entity_details",
            description="Gets detailed information about a specific entity",
            input_schema={"entity_fqn": "string"},
            output_schema={"entity": "Entity", "details": "dict"}
        )
    ]
    
    async def can_handle(self, task_description: str) -> float:
        """
        Determine if this agent can handle the task based on keywords.
        """
        task_lower = task_description.lower()
        discovery_keywords = [
            "list", "show", "find", "discover", "catalog", "entities", 
            "tables", "databases", "schemas", "what tables", "what databases"
        ]
        
        score = 0.0
        for keyword in discovery_keywords:
            if keyword in task_lower:
                score += 0.2
        
        # Cap the score at 1.0
        return min(score, 1.0)
    
    def _build_search_query(self, task: str, entity_type: str = "table") -> str:
        """
        Build an optimized search query from the task description.
        
        The OpenMetadata search works better with specific terms rather than
        natural language questions.
        
        Args:
            task: The original task description
            entity_type: The type of entity being searched for
            
        Returns:
            Optimized search query string
        """
        task_lower = task.lower().strip()
        
        # Handle common patterns - exact match first
        list_all_tables_patterns = [
            "list all tables", "list all table", "show tables", "show all tables",
            "list tables", "show table", "list the tables", "show the tables",
            "get all tables", "get tables", "find tables", "discover tables",
            "list all table entities", "list table entities", "list entities",
            "list all entity", "list entity"
        ]
        if task_lower in list_all_tables_patterns:
            return "table"
        
        # "list databases" -> "database"
        if task_lower in ["list all databases", "list databases", "show databases", "show all databases", "list database entities"]:
            return "database"
        
        # "list schemas" -> "databaseSchema" 
        if task_lower in ["list all schemas", "list schemas", "show schemas", "show all schemas", "list schema entities"]:
            return "databaseSchema"
        
        # Handle patterns like "list all X entities" -> just "X"
        # This regex catches patterns like "list all table entities" -> "table"
        import re
        list_all_pattern = re.match(r'list\s*(?:all\s+)?(\w+)\s*entities?', task_lower)
        if list_all_pattern:
            entity_word = list_all_pattern.group(1)
            if entity_word in ['table', 'tables', 'database', 'databases', 'schema', 'schemas']:
                return "table" if "table" in entity_word else entity_word
        
        # If the task starts with "list" or "show" followed by nothing or just stop words,
        # it's likely a simple list request
        if task_lower.startswith('list ') or task_lower.startswith('show '):
            # Extract what comes after "list" or "show"
            remainder = task_lower
            if remainder.startswith('list '):
                remainder = remainder[5:]
            elif remainder.startswith('show '):
                remainder = remainder[5:]
            
            # Remove common filler words
            stop_words = ['all', 'the', 'your', 'from', 'openmetadata', 'catalog', 'using', 'capability', 'available', 'entities', 'entity', 'with']
            words = remainder.split()
            key_terms = [w for w in words if w not in stop_words and len(w) > 1]
            
            if not key_terms or key_terms[0] in ['tables', 'table', 'databases', 'database', 'schemas', 'schema']:
                return "table"
            
            # If key_terms is short enough, use it
            if len(key_terms) <= 2:
                query = " ".join(key_terms)
                # Make sure it contains entity type
                if not any(t in query for t in ["table", "database", "schema"]):
                    query = f"table {query}"
                return query
        
        # Final fallback: just use "table" for table-related tasks
        if "table" in task_lower or "list" in task_lower:
            return "table"
        
        # Default based on entity type
        return entity_type if entity_type else "table"
    
    async def execute(
        self, 
        task: str, 
        inputs: Dict[str, Any], 
        mcp_client: Any = None
    ) -> AgentFinding:
        """
        Execute the catalog scout's discovery logic.
        
        Args:
            task: The specific task description for this agent
            inputs: Dictionary of input data from the blackboard
            mcp_client: MCP client for interacting with OpenMetadata
            
        Returns:
            AgentFinding containing discovered entities
        """
        logger.info(f"[CatalogScout] Executing task: {task}")
        
        # Get MCP client if not provided
        if mcp_client is None:
            mcp_client = get_mcp_client()
        
        # Determine what type of entities to look for based on task
        entity_type = "table"  # default
        database = None
        
        task_lower = task.lower()
        if "database" in task_lower:
            entity_type = "database"
        elif "schema" in task_lower:
            entity_type = "database_service"  # or schema depending on OpenMetadata
        
        # Extract database from inputs if available
        if inputs and "database" in inputs:
            database = inputs["database"]
        
        try:
            # Use the MCP client to search for entities using keyword search
            # Use search_metadata_all to get ALL results with pagination
            async with mcp_client as client:
                # Build query from task description
                # Clean up the query - remove stop words and use just key terms
                query = self._build_search_query(task)
                
                # Use the pagination method to get all results
                search_result = await client.search_metadata_all(
                    query=query,
                    entity_type=entity_type,
                    max_results=1000  # Get up to 1000 results
                )
                
                # Extract entities from search results
                # The response structure has results at the top level
                entities = search_result.get("results", [])
                total_count = search_result.get("totalFound", len(entities))
                
                # Deduplicate entities by FQN before building details
                # Some search results may contain the same entity multiple times across pages
                unique_by_fqn = {}
                for hit in entities:
                    # Extract FQN from hit, checking multiple possible field paths
                    fqn = (
                        hit.get("fullyQualifiedName") or
                        hit.get("_source", {}).get("fullyQualifiedName") or
                        hit.get("name") or
                        hit.get("_source", {}).get("name") or
                        ""
                    )
                    if fqn and fqn not in unique_by_fqn:
                        unique_by_fqn[fqn] = hit
                
                unique_entities = list(unique_by_fqn.values())
                
                # Create summary - use actual unique count
                summary = f"Found {len(unique_entities)} unique {entity_type}(s) in the catalog"
                
                # Create details - include all unique entities, not just first 10
                details = {
                    "entity_type": entity_type,
                    "query": query,
                    "entities": [
                        {
                            "name": entity.get("name"),
                            "fullyQualifiedName": entity.get("fullyQualifiedName"),
                            "description": entity.get("description"),
                            "service": entity.get("service", {}).get("displayName") if isinstance(entity.get("service"), dict) else None,
                            "database": entity.get("database", {}).get("displayName") if isinstance(entity.get("database"), dict) else None
                        }
                        for entity in unique_entities
                    ],
                    "total_count": total_count,
                    "returned_count": len(unique_entities),
                    "deduplicated": True
                }
                
                # Create finding
                finding = AgentFinding(
                    agent_id=self.agent_id,
                    subtask_id="catalog_discovery",
                    task_description=task,
                    finding_type="classification",  # or maybe a new type for discovery
                    target_entity=None,  # This is a general discovery, not targeting a specific entity
                    summary=summary,
                    details=details,
                    confidence=0.95,  # High confidence in discovery results
                    proposed_actions=[],  # Discovery doesn't propose actions directly
                    mcp_tool_calls=[],  # Would be populated by the MCP client internally
                    llm_reasoning=f"The Catalog Scout discovered {total_count} {entity_type}(s) by querying the OpenMetadata MCP server using search_metadata with pagination. All entities are included in the response."
                )
                
                return finding
                
        except Exception as e:
            logger.error(f"Catalog Scout failed: {str(e)}")
            # Return a finding indicating failure
            finding = AgentFinding(
                agent_id=self.agent_id,
                subtask_id="catalog_discovery",
                task_description=task,
                finding_type="other",
                summary=f"Catalog Scout failed: {str(e)}",
                details={"error": str(e), "entity_type": entity_type},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"An error occurred while attempting to discover entities: {str(e)}"
            )
            return finding


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(CatalogScout())