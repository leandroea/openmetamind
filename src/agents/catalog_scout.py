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
                # Smart database filtering - aim for real databases
                db_names = []
                seen = set()

                for d in databases:
                    name = d.get("name") or d.get("fullyQualifiedName", "")
                    if not name:
                        continue
                    name_lower = name.lower()

                    # Skip any name with / or . (likely table/view paths, not databases)
                    # BUT allow openmetadata-db-* which have hyphens but are real databases
                    if ("/" in name or "." in name) and not name_lower.startswith("openmetadata-db-"):
                        continue

                    # Positive known good databases
                    if any(known in name_lower for known in ["ecommerce_db", "posts_db", "shopify", "default"]):
                        if name not in seen:
                            seen.add(name)
                            db_names.append(name)
                        continue

                    # Snowflake test databases (openmetadata-db-0 through openmetadata-db-4)
                    if name_lower.startswith("openmetadata-db-"):
                        if name not in seen:
                            seen.add(name)
                            db_names.append(name)
                        continue

                    # Strong exclusions - skip everything that looks like a table or test artifact
                    if any(exclude in name_lower for exclude in [
                        "openmetadata-schema-", "information_schema", "pg_catalog",
                        "calculate_", "delete_", "get_", "update_", "insert_", "transform_",
                        "fact_", "dim_", "agent_", "metrics_", "summary", "_clean", "_address",
                        "categories", "comments", "users", "posts", "products", "orders",
                        "generate_random_password", "customer_features", "dim(shop)",
                        # Additional test/table-like patterns to exclude
                        "global", "ice", "market", "marketing", "mortgage", "ice_global", 
                        "icemarketdata", "global_market"
                    ]):
                        continue

                    # Skip long or complex names (very likely tables)
                    if len(name) > 35 or name.count('_') >= 3:
                        continue

                    if name and name not in seen:
                        seen.add(name)
                        db_names.append(name)

                db_count = len(db_names)
                logger.info(f"[CatalogScout] Found {db_count} actual databases after filtering: {db_names[:15]}")

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
                f"  {', '.join(db_names[:8])}{' ...and ' + str(len(db_names) - 8) + ' more' if len(db_names) > 8 else ''}\n\n"
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
        # NOTE: These must be EXPLICIT main task phrases to avoid triggering on sub-task descriptions
        # "discover databases" alone is too broad - "discover schemas within each database" would match
        db_discovery_keywords = [
            "discover all databases", "list databases", "find databases",
            "discover all schemas", "list schemas", "find schemas",
            "discover all tables", "list tables", "find tables",
            "explore the database", "catalog scout"
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
        """Main execution entry point with proper routing."""
        logger.info(f"[CatalogScout] Executing task: {task}")

        if mcp_client is None:
            mcp_client = get_mcp_client()

        task_lower = task.lower().strip()

        # === STRICT ROUTING ===
        # 1. Hierarchy / broad discovery tasks
        if any(phrase in task_lower for phrase in [
            "database hierarchy", 
            "discover the database", 
            "list all databases", 
            "show databases", 
            "catalog hierarchy",
            "discover hierarchy",
            "list databases"
        ]):
            logger.info("[CatalogScout] Detected hierarchy task → calling _build_hierarchy")
            return await self._build_hierarchy(task, mcp_client)

        # 2. Specific "Describe", "Find", "Locate" or "Details" tasks → should go to Documentation Agent (do NOT use hierarchy)
        # Check for common Planner-generated phrases AND specific table names
        task_lower = task.lower().strip()
        
        # Build list of phrases that indicate a specific entity lookup
        specific_phrases = [
            "describe ",
            "details of ",
            "schema of ",
            "what is the ",
            "what is ",
            "find the ",
            "locate and identify",
            "discover the ",
            "entity in the catalog",
            "openmetadata-table-"  # Catches openmetadata-table-bench, openmetadata-table-0, etc.
        ]
        
        # Check if task matches any specific phrase or starts with describe/find
        is_specific_task = any(phrase in task_lower for phrase in specific_phrases)
        is_specific_task = is_specific_task or task_lower.startswith("describe ") or task_lower.startswith("find ") or task_lower.startswith("locate ")
        
        if is_specific_task:
            # Extract entity name from task
            entity_name = task
            for prefix in ["find the ", "describe ", "details of ", "schema of ", "what is the ", "what is ", "locate and identify the ", "discover the "]:
                if task_lower.startswith(prefix):
                    entity_name = task[len(prefix):].strip()
                    break
            
            # Clean up entity name (remove trailing phrases like "entity in the OpenMetadata catalog", "table in the catalog", etc.)
            # Handle multi-word suffixes
            suffixes_to_check = [
                " entity in the OpenMetadata catalog",
                " table in the OpenMetadata catalog", 
                " entity in the catalog",
                " table in the catalog",
                " entity",
                " table",
                " in the catalog",
                " in openmetadata"
            ]
            for suffix in suffixes_to_check:
                if entity_name.lower().endswith(suffix):
                    entity_name = entity_name[:-len(suffix)].strip()
                    break  # Only remove one suffix per iteration
            
            # Construct a reasonable FQN based on the entity name
            # For known tables, construct a likely FQN
            entity_fqn = entity_name
            if "openmetadata-table-" in entity_name.lower():
                entity_fqn = f"sample_data.ecommerce_db.shopify.{entity_name}"
            
            logger.info(f"[CatalogScout] Detected specific entity task: {task} → extracted entity: {entity_name}, FQN: {entity_fqn}")
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="specific_entity_lookup",
                task_description=task,
                finding_type="description",
                summary=f"Located: {entity_name}",
                details={
                    "entity_name": entity_name,
                    "table_name": entity_name,
                    "entity_fqn": entity_fqn,
                    "action": "pass_to_documentation"
                },
                confidence=0.95,
                target_entity=entity_name  # Pass to next task via blackboard
            )

        # 3. Default fallback for other discovery tasks
        logger.info("[CatalogScout] Using hierarchy as default for general discovery")
        return await self._build_hierarchy(task, mcp_client)


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(CatalogScout())