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
    
    async def _build_hierarchy(self, task: str, mcp_client) -> AgentFinding:
        """Build and summarize the real database hierarchy."""
        logger.info("[CatalogScout] Starting hierarchy discovery with correct entity types")
        
        try:
            async with mcp_client as client:
                # 1. Databases
                db_result = await client.search_metadata_all(
                    query="",
                    entity_type="database",
                    max_results=100
                )
                databases = db_result.get("hits", db_result.get("data", db_result.get("results", [])))
                # Filter to get actual databases (not tables, functions, or other entities)
                # Real database names are simple, short names - not verb phrases or long names
                non_db_patterns = [
                    # System databases - NOT actual user databases (skip these)
                    "information_schema", "pg_catalog", "sys", 
                    "performance_schema", "mysql", "master", "tempdb", "model", "msdb",
                    # Procedural/database function prefixes (likely not databases)
                    "calculate_", "delete_", "get_", "update_", "insert_", "transform_",
                    "drop_", "create_", "alter_", "exec_", "execute_",
                    # Likely table/entity name prefixes  
                    "agent_", "fact_", "dim_", "marketing_", "global_", "ice_",
                    "_summary", "_metrics", "_daily", "_clean", "_address", "_location",
                    "_staff", "_events", "_line_item", "_order", "_sale", "_session",
                    "_transactions", "_product", "_shop", "_variant",
                    # Common table/entity names that shouldn't be databases
                    "Categories", "Comments", "Users", "Posts", "Products", 
                    "Orders", "Inventory", "Settings", "Config", "Logs",
                    "Events", "Tasks", "Jobs", "History", "Archive",
                    "Tags", "Permissions", "Roles", "Sessions", "Tokens",
                    "Analytics", "Widgets", "Pages", "Views", "Metrics",
                    # Plural forms common in data catalogs
                    "dim(", "fact(", "agg_", "temp_"
                ]
                db_names = []
                for d in databases:
                    name = d.get("name") or d.get("fullyQualifiedName", "")
                    name_lower = name.lower()
                    # Skip if name matches any non-db pattern
                    if any(pattern in name_lower for pattern in non_db_patterns):
                        continue
                    # Skip names with underscores starting with common verb prefixes (likely functions/procs)
                    if any(name_lower.startswith(p) for p in ["calculate", "delete", "get", "update", "insert", "transform", "drop", "create", "alter", "exec"]):
                        continue
                    # Skip names that look like schema names (e.g., openmetadata-schema-0, shopify_schema)
                    if "-schema" in name_lower or name_lower.startswith("schema_"):
                        continue
                    # Skip names that look like table/entity names (have multiple underscores - snake_case tables)
                    if name.count('_') >= 2:
                        continue
                    # Skip very long names (likely FQN fragments or full query names)
                    if len(name) > 30:
                        continue
                    # Skip if not a simple name at all
                    if not name or " " in name:
                        continue
                    if name and name not in db_names:
                        db_names.append(name)
                db_count = len(db_names)
                logger.info(f"[CatalogScout] Found {db_count} actual databases: {db_names[:10]}")

                # 2. Schemas (broad search - OpenMetadata usually has fewer)
                schema_result = await client.search_metadata_all(
                    query="",
                    entity_type="databaseSchema",
                    max_results=200
                )
                schemas = schema_result.get("hits", schema_result.get("data", schema_result.get("results", [])))
                schema_count = len(schemas)
                logger.info(f"[CatalogScout] Found {schema_count} schemas")

                # 3. Tables (sample for count + examples)
                table_result = await client.search_metadata_all(
                    query="",
                    entity_type="table",
                    max_results=1000
                )
                tables = table_result.get("hits", table_result.get("data", table_result.get("results", [])))
                table_count_approx = (len(tables) / min(len(tables), 50)) * 1000 if len(tables) > 0 else 0
                sample_tables = [t.get("name") for t in tables[:8]]
                logger.info(f"[CatalogScout] Found {len(tables)} tables in sample, approx {int(table_count_approx)} total")

            # Rich summary for user
            summary = (
                f"✅ **Database Hierarchy Discovered**\n\n"
                f"• **Databases**: {db_count} total\n"
                f"  {', '.join(db_names[:10])}{'...' if len(db_names) > 10 else ''}\n\n"
                f"• **Schemas**: {schema_count} total\n"
                f"• **Tables**: ~{int(table_count_approx):,} in the catalog\n"
                f"  Sample tables: {', '.join(sample_tables) if sample_tables else 'None sampled'}\n"
            )

            # Structured details for blackboard / future rendering
            details = {
                "databases": db_names,
                "database_count": db_count,
                "schema_count": schema_count,
                "table_count_approx": int(table_count_approx),
                "sample_tables": sample_tables,
                "raw_databases": [d.get("fullyQualifiedName") for d in databases[:5]]
            }

            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="discover_db_hierarchy",
                task_description=task,
                finding_type="other",
                summary=summary,
                details=details,
                confidence=0.92,
                target_entity=None,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning="Used search_metadata with entityType=database, databaseSchema, table and empty query for full discovery."
            )

        except Exception as e:
            logger.error(f"[CatalogScout] Hierarchy discovery error: {e}", exc_info=True)
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="discover_db_hierarchy",
                task_description=task,
                finding_type="other",
                summary=f"Error discovering hierarchy: {str(e)}",
                details={"error": str(e)},
                confidence=0.5,
                target_entity=None,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"Error during hierarchy discovery: {str(e)}"
            )
    
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
        
        # Hierarchy building keywords
        hierarchy_keywords = [
            "hierarchy", "hierarchical", "relationships", "structure",
            "database hierarchy", "schema hierarchy", "nested"
        ]
        
        # Keywords for discovering databases specifically
        db_discovery_keywords = [
            "discover databases", "list databases", "find databases",
            "discover schemas", "list schemas", "find schemas",
            "discover tables", "list tables", "find tables",
            "discover all", "catalog scout", "explore the"
        ]
        
        # Check if task mentions hierarchy
        if any(kw in task_lower for kw in hierarchy_keywords):
            return "_build_hierarchy"
        
        # Check if task is about discovering databases/schemas/tables (uses "discover all" or similar)
        if any(kw in task_lower for kw in db_discovery_keywords):
            return "_build_hierarchy"
        
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
        
        # Extract snake_case/camelCase entity names (words with 2+ underscores)
        # These are specific entity names like "big_data_table_with_nested_columns"
        underscore_words = [w for w in task.split() if w.count('_') >= 2]
        if underscore_words:
            # Return the first underscore word as the query - it's likely a specific entity name
            return underscore_words[0]
        
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
        # Priority: explicit entity type in task > "table" > "database" > "schema"
        if "table" in task_lower:
            entity_type = "table"
        elif "database" in task_lower:
            entity_type = "database"
        elif "schema" in task_lower:
            entity_type = "database_service"  # OpenMetadata uses database_service for schemas
        
        # Extract database from inputs if available
        if inputs and "database" in inputs:
            database = inputs["database"]
        
        try:
            # Determine if this is a hierarchy task (only for the main hierarchy discovery task)
            # Sub-tasks like "discover schemas" should NOT trigger hierarchy building
            task_lower = task.lower()
            is_hierarchy_task = (
                "discover the database hierarchy" in task_lower or
                "discover full database hierarchy" in task_lower or
                "list all databases" in task_lower or
                "list the database hierarchy" in task_lower
            )
            
            if is_hierarchy_task:
                return await self._build_hierarchy(task, mcp_client)
            
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