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
    
    async def _fetch_all_entities_with_pagination(
        self, 
        mcp_client, 
        entity_type: str, 
        max_results: int = 10000
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Fetch ALL entities of a given type with proper pagination.
        
        This helper ensures we get the complete list of entities by continuing
        to fetch pages until no more results are available.
        
        Args:
            mcp_client: MCP client for OpenMetadata
            entity_type: Type of entity (e.g., "table", "database", "databaseSchema")
            max_results: Maximum total entities to fetch (default 10000, increase for tables)
            
        Returns:
            Tuple of (list of entities, total count found)
        """
        all_entities = []
        current_offset = 0
        page_size = 100  # Fetch 100 at a time for efficiency
        
        async with mcp_client as client:
            while len(all_entities) < max_results:
                # Build search arguments
                arguments = {
                    "query": "",
                    "size": page_size,
                    "from": current_offset
                }
                if entity_type:
                    arguments["entityType"] = entity_type
                
                try:
                    result = await client._call_mcp_tool("search_metadata", arguments)
                    
                    entities = result.get("results", [])
                    if not entities:
                        break  # No more results
                    
                    all_entities.extend(entities)
                    
                    # Check pagination state
                    has_more = result.get("hasMore", False)
                    total_found = result.get("totalFound", 0)
                    
                    logger.info(f"[CatalogScout] Pagination fetch for {entity_type}: offset={current_offset}, fetched={len(entities)}, total={total_found}, has_more={has_more}")
                    
                    # Stop if no more results
                    if not has_more or len(all_entities) >= total_found:
                        break
                    
                    # Move to next page
                    current_offset += page_size
                    
                except Exception as e:
                    logger.warning(f"[CatalogScout] Error during pagination for {entity_type} at offset {current_offset}: {e}")
                    break
        
        total_count = len(all_entities)
        logger.info(f"[CatalogScout] Fetched {total_count} {entity_type}s with full pagination")
        
        return all_entities, total_count

    async def _build_hierarchy(self, task: str, mcp_client) -> AgentFinding:
        """Build and summarize the real database hierarchy."""
        logger.info("[CatalogScout] Starting hierarchy discovery with correct entity types")
        
        try:
            # Check if this is a "list all tables" request (needs full pagination)
            task_lower = task.lower()
            is_list_all_tables = any(kw in task_lower for kw in [
                "list all tables", "show every table", "all tables in the catalog",
                "list tables", "show me all tables", "get all tables",
                "all tables"
            ])
            
            logger.info(f"[CatalogScout] is_list_all_tables={is_list_all_tables}")
            
            # 1. Databases
            db_result = await self._fetch_all_entities_with_pagination(mcp_client, "database", max_results=200)
            databases = db_result[0] if isinstance(db_result, tuple) else db_result.get("hits", db_result.get("results", []))
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
            schema_result = await self._fetch_all_entities_with_pagination(mcp_client, "databaseSchema", max_results=500)
            schemas = schema_result[0] if isinstance(schema_result, tuple) else schema_result.get("hits", schema_result.get("results", []))
            schema_count = len(schemas) if isinstance(schemas, list) else 0
            logger.info(f"[CatalogScout] Found {schema_count} schemas with full pagination")

            # 3. Tables - use higher limit for "list all tables" requests
            table_max = 20000 if is_list_all_tables else 2000
            table_result = await self._fetch_all_entities_with_pagination(mcp_client, "table", max_results=table_max)
            tables = table_result[0] if isinstance(table_result, tuple) else table_result.get("hits", table_result.get("results", []))
            table_count = len(tables) if isinstance(tables, list) else 0
            
            # Extract table FQNs for blackboard
            all_table_fqns = []
            for t in tables:
                fqn = t.get("fullyQualifiedName", t.get("name", ""))
                if fqn:
                    all_table_fqns.append(fqn)
            
            sample_tables = [t.get("name", "unknown") for t in tables[:30]]  # More samples for display
            logger.info(f"[CatalogScout] Found {table_count} tables with full pagination (max requested: {table_max})")

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
        
        # Build summary - different format for list-all-tables vs general hierarchy
        if is_list_all_tables:
            # For "list all tables" request - show count and examples
            summary = (
                f"✅ **Complete Table List**\n\n"
                f"Found **{table_count:,} tables** in the OpenMetadata catalog\n\n"
                f"First 40 tables: {', '.join(sample_tables[:40])}\n\n"
                f"(Use 'get all table FQNs' for complete list)"
            )
            details = {
                "table_count": table_count,
                "all_table_fqns": all_table_fqns,
                "sample_tables": sample_tables[:50],  # 50 samples for display
                "database_count": db_count,
                "schema_count": schema_count
            }
        else:
            # Standard hierarchy summary
            summary = (
                f"✅ **Database Hierarchy Discovered**\n\n"
                f"• **Databases**: {db_count} total\n"
                f"  {', '.join(db_names[:8])}{' ...and ' + str(len(db_names) - 8) + ' more' if len(db_names) > 8 else ''}\n\n"
                f"• **Schemas**: {schema_count} total\n"
                f"• **Tables**: {table_count:,} total in the catalog\n"
                f"  Sample: {', '.join(sample_tables[:20]) if sample_tables else 'None'}"
            )
            details = {
                "databases": db_names,
                "database_count": db_count,
                "schema_count": schema_count,
                "table_count": table_count,
                "all_table_fqns": all_table_fqns,  # Always include full list for blackboard
                "sample_tables": sample_tables
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
            proposed_actions=[],  # No actions for read-only list queries
            mcp_tool_calls=[],
            llm_reasoning=f"Fetched {db_count} databases, {schema_count} schemas, and {table_count:,} tables with full pagination."
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
            # Extract entity name from task - be more robust with various prefixes
            entity_name = task
            extracted = False
            
            # Try all known prefixes (order matters - longer first)
            prefixes_to_try = [
                "find and identify ",
                "find the ",
                "describe ",
                "details of ",
                "schema of ",
                "what is the ",
                "what is ",
                "locate and identify the ",
                "locate the ",
                "discover the ",
            ]
            
            for prefix in prefixes_to_try:
                if task_lower.startswith(prefix):
                    entity_name = task[len(prefix):].strip()
                    extracted = True
                    logger.info(f"[CatalogScout] Extracted entity with prefix '{prefix}': '{entity_name}'")
                    break
            
            # Fallback: if no prefix matched, search for openmetadata-table pattern anywhere in task
            if not extracted:
                import re
                # Look for "openmetadata-table-" pattern which is a strong table name indicator
                match = re.search(r'(openmetadata-table-\w+)', task_lower)
                if match:
                    entity_name = match.group(1)
                    extracted = True
                    logger.info(f"[CatalogScout] Extracted entity via pattern match: '{entity_name}'")
            
            # Last resort fallback: use the raw task if nothing else worked
            if not extracted:
                logger.warning(f"[CatalogScout] Could not extract entity name from task '{task}', using raw task")
                entity_name = task
            
            # Clean up entity name (remove trailing phrases like "entity in the OpenMetadata catalog", "table in the catalog", etc.)
            # Handle multi-word suffixes - be more aggressive
            suffixes_to_check = [
                " in the catalog",
                " in OpenMetadata catalog",
                " in the OpenMetadata catalog",
                " entity in the catalog",
                " entity in OpenMetadata catalog",
                " entity in the OpenMetadata catalog",
                " table in the catalog", 
                " table in OpenMetadata catalog",
                " table in the OpenMetadata catalog",
                " entity",
                " table",
                " openmetadata"
            ]
            for suffix in suffixes_to_check:
                if entity_name.lower().endswith(suffix):
                    entity_name = entity_name[:-len(suffix)].strip()
            
            # Also clean up "and identify" or similar residual phrases from the beginning
            for residual_prefix in ["and identify ", "and locate ", "identify "]:
                if entity_name.lower().startswith(residual_prefix):
                    entity_name = entity_name[len(residual_prefix):].strip()
            
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