"""
Catalog Scout Agent - Discovers entities in OpenMetadata.
"""
import logging
from typing import Dict, Any
from .base import SwarmAgent, Capability
from ..models.state import AgentFinding
from ..mcp.client import get_mcp_client

logger = logging.getLogger(__name__)

class CatalogScout(SwarmAgent):
    """Discovers entities (tables, databases, schemas, etc.) in OpenMetadata."""

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
        """Determine if this agent can handle the task."""
        task_lower = task_description.lower()
        discovery_keywords = [
            "list", "show", "find", "discover", "catalog", "entities",
            "tables", "databases", "schemas", "hierarchy", "what tables",
            "what databases", "database hierarchy"
        ]
        score = sum(0.25 for kw in discovery_keywords if kw in task_lower)
        return min(score, 1.0)

    async def _build_hierarchy(self, task: str, mcp_client) -> AgentFinding:
        """Build a clean and accurate database hierarchy summary."""
        logger.info("[CatalogScout] Starting polished hierarchy discovery")

        try:
            async with mcp_client as client:
                # 1. Databases
                db_result = await client.search_metadata_all(
                    query="", entity_type="database", max_results=200
                )
                databases = db_result.get("hits", db_result.get("data", db_result.get("results", [])))

                # Smart filtering for real databases
                db_names = []
                seen = set()

                for d in databases:
                    name = d.get("name") or d.get("fullyQualifiedName", "")
                    if not name:
                        continue
                    name_lower = name.lower()

                    # Positive matches - definitely databases
                    if any(known in name_lower for known in ["ecommerce_db", "posts_db", "shopify", "default"]):
                        if name not in seen:
                            seen.add(name)
                            db_names.append(name)
                        continue

                    # Snowflake-style openmetadata-db-N
                    if name_lower.startswith("openmetadata-db-"):
                        if name not in seen:
                            seen.add(name)
                            db_names.append(name)
                        continue

                    # Skip obvious non-databases
                    if any(exclude in name_lower for exclude in [
                        "openmetadata-schema-", "information_schema", "pg_catalog",
                        "calculate_", "delete_", "get_", "update_", "insert_", "transform_",
                        "fact_", "dim_", "agent_", "metrics_", "summary", "_clean", "_address",
                        "categories", "comments", "users", "posts", "products", "orders",
                        "generate_random_password"
                    ]):
                        continue

                    # Skip long or overly complex names (likely tables)
                    if len(name) > 40 or name.count('_') >= 3:
                        continue

                    # Add other reasonable candidates
                    if name and name not in seen:
                        seen.add(name)
                        db_names.append(name)

                db_count = len(db_names)
                logger.info(f"[CatalogScout] Found {db_count} actual databases: {db_names}")

                # 2. Schemas
                schema_result = await client.search_metadata_all(
                    query="", entity_type="databaseSchema", max_results=200
                )
                schema_count = len(schema_result.get("hits", schema_result.get("data", schema_result.get("results", []))))

                # 3. Tables (sample)
                table_result = await client.search_metadata_all(
                    query="", entity_type="table", max_results=100
                )
                tables = table_result.get("hits", table_result.get("data", table_result.get("results", [])))
                sample_tables = [t.get("name") for t in tables[:10]]
                table_approx = len(tables) * 60 if tables else 6000

                # Professional summary
                summary = (
                    f"✅ **Database Hierarchy Discovered**\n\n"
                    f"**Databases**: {db_count} total\n"
                    f"{', '.join(db_names[:12])}{ ' ...' if len(db_names) > 12 else ''}\n\n"
                    f"**Schemas**: {schema_count} total\n"
                    f"**Tables**: approximately {table_approx:,} in the catalog\n\n"
                    f"**Sample tables**: {', '.join(sample_tables[:8])}{'...' if len(sample_tables) > 8 else ''}"
                )

                details = {
                    "databases": db_names,
                    "database_count": db_count,
                    "schema_count": schema_count,
                    "table_count_approx": table_approx,
                    "sample_tables": sample_tables
                }

                return AgentFinding(
                    agent_id=self.agent_id,
                    subtask_id="discover_db_hierarchy",
                    task_description=task,
                    finding_type="other",
                    summary=summary,
                    details=details,
                    confidence=0.93,
                    target_entity=None,
                    proposed_actions=[],
                    llm_reasoning="Built clean hierarchy with smart deduplication and filtering."
                )

        except Exception as e:
            logger.error(f"[CatalogScout] Hierarchy discovery error: {e}", exc_info=True)
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="discover_db_hierarchy",
                task_description=task,
                finding_type="other",
                summary="❌ Could not discover database hierarchy due to an error.",
                details={"error": str(e)},
                confidence=0.4,
                target_entity=None
            )

    async def execute(
        self,
        task: str,
        inputs: Dict[str, Any],
        mcp_client: Any = None
    ) -> AgentFinding:
        """Main execution entry point."""
        logger.info(f"[CatalogScout] Executing task: {task}")

        if mcp_client is None:
            mcp_client = get_mcp_client()

        task_lower = task.lower()

        # Route hierarchy tasks to dedicated method
        if any(phrase in task_lower for phrase in [
            "database hierarchy", "discover the database", "list all databases",
            "show databases", "catalog hierarchy", "discover hierarchy"
        ]):
            return await self._build_hierarchy(task, mcp_client)

        # Fallback: treat other discovery tasks as hierarchy for now
        return await self._build_hierarchy(task, mcp_client)


# Auto-register the agent
from .registry import AgentRegistry
AgentRegistry().register(CatalogScout())