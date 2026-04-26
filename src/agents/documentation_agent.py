"""
Documentation Agent - Finds and documents undocumented entities in OpenMetadata.
"""

import asyncio
import logging
import os
from typing import Dict, Any, List

from .base import SwarmAgent, Capability
from ..models.state import AgentFinding, ProposedAction, ActionType
from ..mcp.client import get_mcp_client
from ..utils import strip_think

logger = logging.getLogger(__name__)


class DocumentationAgent(SwarmAgent):
    """
    Specialized agent that finds undocumented entities and generates
    business-friendly descriptions for them.
    """
    
    agent_id = "documentation_agent"
    display_name = "Documentation Agent"
    description = "Finds undocumented entities and generates business-friendly descriptions"
    avatar_emoji = "📝"
    
    capabilities = [
        Capability(
            name="find_undocumented",
            description="Finds tables and columns missing descriptions",
            input_schema={"database": "string", "schema": "string"},
            output_schema={"undocumented": "list[Entity]", "count": "integer"}
        ),
        Capability(
            name="generate_description",
            description="Generates business-friendly descriptions via LLM",
            input_schema={"entity_context": "dict"},
            output_schema={"description": "string", "confidence": "float"}
        ),
        Capability(
            name="document_entities",
            description="Full pipeline to document undocumented entities",
            input_schema={"database": "string", "schema": "string"},
            output_schema={"documented": "list[Entity]", "proposed_actions": "list[Action]"}
        )
    ]
    
    def __init__(self):
        """Initialize the Documentation Agent with LLM client."""
        self.llm = None  # Lazy initialization
        
    def _get_llm(self):
        """Get or create LLM client."""
        if self.llm is None:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
                api_key=os.getenv("MINIMAX_API_KEY"),
                model=os.getenv("LLM_MODEL", "minimax-m2.7"),
                temperature=0.3,
                max_tokens=1000
            )
        return self.llm
    
    async def can_handle(self, task_description: str) -> float:
        """
        Determine if this agent can handle documentation tasks.
        """
        task_lower = task_description.lower()
        doc_keywords = [
            "document", "description", "readme", "missing doc",
            "describe", "undocumented", "empty description",
            "no description", "fill in", "add description"
        ]
        
        score = 0.0
        for keyword in doc_keywords:
            if keyword in task_lower:
                score += 0.25
        
        return min(score, 1.0)
    
    def _extract_database_from_task(self, task: str) -> str:
        """Extract database name from task description."""
        task_lower = task.lower()
        
        # Handle "customers database" -> "customers"
        import re
        patterns = [
            r'(\w+)\s+database',
            r'database\s+(\w+)',
            r'(\w+)\s+db',
            r'db\s+(\w+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, task_lower)
            if match:
                return match.group(1)
        
        return None  # No database found - will use other context

    def _extract_table_name_from_task(self, task: str) -> str:
        """
        Extract a specific table/entity name from task description.
        
        Looks for snake_case words (2+ underscores) which are likely specific
        entity names like 'big_data_table_with_nested_columns' or 'customer_features'.
        """
        words = task.split()
        for word in words:
            if word.count('_') >= 2:
                return word
        return None
    
    # Placeholder strings that indicate no real description exists
    _PLACEHOLDER_DESCRIPTIONS = {
        "no description",
        "no description available",
        "n/a",
        "none",
        "null",
        "undefined",
        "field_missing",
    }

    def _is_missing_description(self, description: str, entity_name: str = None) -> bool:
        """
        Check if a description is missing or too short to be useful.
        
        A description is considered missing if:
        - It is None, empty, or whitespace-only
        - It matches a known placeholder string (case-insensitive)
        - It is just a repetition of the entity name
        - It is shorter than 10 characters (too short to be useful)
        """
        if not description:
            return True
        
        desc_lower = description.lower().strip()
        
        # Check against placeholder strings
        if desc_lower in self._PLACEHOLDER_DESCRIPTIONS:
            return True
        
        # Check if description is just a repetition of the entity name
        if entity_name:
            entity_lower = entity_name.lower().strip()
            # Remove fully qualified name parts for simpler comparison
            if desc_lower == entity_lower or desc_lower == entity_lower.split('.')[-1]:
                return True
        
        if len(description.strip()) < 10:
            return True
        
        return False
    
    def _is_explain_task(self, task: str) -> bool:
        """
        Detect if task is asking for explanation/analysis rather than documentation.
        
        Tasks like "Explain nested columns in X" or "Analyze structure of X"
        are read-only and should return text explanations, not proposed actions.
        """
        task_lower = task.lower()
        explain_keywords = [
            "explain",
            "describe structure",
            "analyze structure",
            "what columns",
            "what fields",
            "show me the",
            "understand the",
            "breakdown of",
            "nested",
            "hierarchy",
        ]
        
        # Also check for negative documentation indicators
        doc_keywords = [
            "document",
            "add description",
            "fill in",
            "missing description",
        ]
        
        has_explain = any(kw in task_lower for kw in explain_keywords)
        has_doc_only = all(kw in task_lower for kw in doc_keywords)
        
        # It's an explain task if it has explain keywords and not purely documentation
        return has_explain and not has_doc_only
    
    async def _explain_nested_columns(
        self,
        task: str,
        inputs: Dict[str, Any],
        mcp_client
    ) -> AgentFinding:
        """
        Explain mode: Analyze entity structure and return text explanation.
        
        This is a read-only analysis task - no proposed actions are generated.
        
        Args:
            task: The explanation task description
            inputs: Input data from blackboard
            mcp_client: MCP client for OpenMetadata
            
        Returns:
            AgentFinding with text explanation in summary/details
        """
        logger.info(f"[DocumentationAgent] Explain mode: {task}")
        
        logger.info(f"[_explain_nested_columns] inputs received: {inputs}")
        logger.info(f"[_explain_nested_columns] table_fqn from inputs: {inputs.get('table_fqn')}")
        
        # Extract table/entity name from task
        table_fqn = inputs.get("table_fqn") or inputs.get("entity_fqn")
        if not table_fqn:
            table_fqn = self._extract_table_name_from_task(task) or self._extract_database_from_task(task)
        
        if not table_fqn:
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="explain_structure",
                task_description=task,
                finding_type="description",
                target_entity=None,
                summary="No entity specified for explanation",
                details={},
                confidence=1.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning="Cannot explain without a target entity."
            )
        
        try:
            # Fetch entity details
            context = await self._gather_context(table_fqn, mcp_client)
            
            # Build column info for LLM
            columns_info = ""
            columns = context.get("columns", [])
            if columns:
                col_lines = []
                for col in columns[:20]:  # Limit to first 20
                    col_lines.append(
                        f"  - {col.get('name', 'unknown')} ({col.get('dataType', 'unknown')}): "
                        f"{col.get('description', 'No description')[:100]}"
                    )
                columns_info = "\nColumns:\n" + "\n".join(col_lines)
            
            tags_str = ", ".join(context.get("tags", [])) or "None"
            
            # Generate explanation via LLM
            llm = self._get_llm()
            prompt = f"""You are a data analyst explaining table structure. 
Provide a clear explanation of this table's columns and their meaning.

Table: {context.get('displayName', table_fqn)}
Database: {context.get('database', 'Unknown')}
Tags: {tags_str}
{columns_info}

Based on the column names and types, explain:
1. What kind of data this table contains
2. The structure and hierarchy of columns
3. Any nested or complex column relationships

Be concise but informative. Do not suggest actions - just explain what you observe."""

            response = await llm.ainvoke(prompt)
            explanation = response.content if hasattr(response, 'content') else str(response)
            explanation = strip_think(explanation).strip()
            
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="explain_structure",
                task_description=task,
                finding_type="description",
                target_entity=table_fqn,
                summary=explanation[:500] if len(explanation) > 500 else explanation,
                details={
                    "table_fqn": table_fqn,
                    "column_count": len(columns),
                    "columns": [
                        {"name": c.get("name"), "type": c.get("dataType")} 
                        for c in columns[:20]
                    ],
                    "tags": context.get("tags", []),
                    "full_explanation": explanation
                },
                confidence=0.9,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning="Explained table structure based on column metadata."
            )
            
        except Exception as e:
            logger.warning(f"Explain mode failed: {e}")
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="explain_structure",
                task_description=task,
                finding_type="description",
                target_entity=table_fqn,
                summary=f"Explanation failed: {str(e)}",
                details={"error": str(e)},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"Error during explanation: {str(e)}"
            )
    
    async def _discover_undocumented_entities(
        self,
        mcp_client,
        search_query: str = None
    ) -> List[Dict[str, Any]]:
        """
        Step A - Discover undocumented entities.
        
        Args:
            mcp_client: MCP client for OpenMetadata
            search_query: Query to scope search - can be a table name, database, or "table"
                      If "table" is passed, will do a full catalog scan for undocumented.
                      
        Returns:
            List of undocumented entities with their context
        """
        undocumented = []
        
        try:
            # Special case: if query is "table" or empty, do a full scan for undocumented
            # This handles "find undocumented tables" type requests
            if search_query is None or search_query.lower() in ["table", "tables", ""]:
                logger.info(f"[_discover_undocumented_entities] Full scan mode for undocumented tables")
                # Use pagination to get ALL tables
                all_entities = []
                current_offset = 0
                page_size = 100
                total_count = 0
                
                async with mcp_client as client:
                    while len(all_entities) < 10000:  # max_results = 10000
                        arguments = {
                            "query": "",
                            "size": page_size,
                            "from": current_offset,
                            "entityType": "table"
                        }
                        
                        try:
                            result = await client._call_mcp_tool("search_metadata", arguments)
                            entities = result.get("results", [])
                            if not entities:
                                break
                            
                            all_entities.extend(entities)
                            fetched_count = len(entities)
                            has_more = result.get("hasMore", False)
                            total_found = result.get("totalFound", 0)
                            total_count = total_found
                            
                            logger.info(f"[_discover_undocumented_entities] Pagination: fetched {len(all_entities)}/{total_found}")
                            
                            if total_found > 0 and len(all_entities) >= total_found:
                                break
                            
                            current_offset += fetched_count
                        except Exception as e:
                            logger.warning(f"[_discover_undocumented_entities] Error at offset {current_offset}: {e}")
                            break
                
                logger.info(f"[_discover_undocumented_entities] Full scan fetched {len(all_entities)} entities")
            else:
                # Use search for specific queries
                logger.info(f"[_discover_undocumented_entities] Search mode for query: '{search_query}'")
                async with mcp_client as client:
                    search_result = await client.search_metadata_all(
                        query=search_query,
                        entity_type="table",
                        max_results=100
                    )
                    all_entities = search_result.get("results", [])
                    logger.info(f"[_discover_undocumented_entities] Search returned {len(all_entities)} entities")
                
                logger.info(f"[_discover_undocumented_entities] Processing {len(all_entities)} entities for undocumented check")
                for entity in all_entities[:5]:
                    name = entity.get("fullyQualifiedName", entity.get("name", "UNKNOWN"))
                    desc = entity.get("description", "FIELD_MISSING")
                    logger.info(f"Entity: {name} | Description: '{desc}' | Missing: {self._is_missing_description(desc, name)}")
                
                for entity in all_entities:
                    name = entity.get("fullyQualifiedName", entity.get("name", ""))
                    description = entity.get("description", "FIELD_MISSING")
                    
                    if self._is_missing_description(description, entity_name=name):
                        # Gather context for this entity
                        context = {
                            "name": name,
                            "displayName": entity.get("displayName", name),
                            "description": description,
                            "database": entity.get("database", {}).get("displayName") if isinstance(entity.get("database"), dict) else None,
                            "service": entity.get("service", {}).get("displayName") if isinstance(entity.get("service"), dict) else None,
                            "tags": [t.get("tagFQN", "").split(".")[-1] for t in entity.get("tags", [])],
                            "columns": entity.get("columns", [])
                        }
                        undocumented.append(context)
                
                logger.info(f"[_discover_undocumented_entities] Found {len(undocumented)} undocumented entities")
                
        except Exception as e:
            logger.error(f"Error discovering undocumented entities: {e}")
        
        return undocumented
    
    async def _search_specific_table(self, mcp_client, table_name: str) -> List[Dict[str, Any]]:
        """
        Search for a specific table by name, return it if undocumented.
        
        Args:
            mcp_client: MCP client for OpenMetadata
            table_name: Table name or FQN to search for
            
        Returns:
            List of undocumented entities matching the table name
        """
        undocumented = []
        
        try:
            async with mcp_client as client:
                # Extract just the table name part (last segment after any dots)
                table_part = table_name.split(".")[-1] if "." in table_name else table_name
                
                # Try get_entity_details first - handle various FQN formats
                # The FQN could be: service.database.schema.table or just table name
                logger.info(f"[_search_specific_table] Looking for table: '{table_name}' (part: '{table_part}')")
                
                # Try search first to find the actual FQN
                search_result = await client.search_metadata_all(
                    query=table_part,
                    entity_type="table",
                    max_results=20
                )
                
                entities = search_result.get("results", [])
                logger.info(f"[_search_specific_table] Search returned {len(entities)} entities for query '{table_part}'")
                
                for entity in entities:
                    fqn = entity.get("fullyQualifiedName", "")
                    display_name = entity.get("displayName", fqn)
                    description = entity.get("description", "FIELD_MISSING")
                    
                    logger.info(f"[_search_specific_table] Checking entity: fqn='{fqn}', displayName='{display_name}', desc='{description[:50] if description else 'None'}...'")
                    
                    # Match if the table part or full name appears in the FQN
                    if table_name.lower() in fqn.lower() or table_part.lower() in fqn.lower():
                        logger.info(f"[_search_specific_table] MATCHED entity: {fqn}")
                        
                        # Even if it HAS description, include it for "describe" use case
                        context = {
                            "name": fqn,
                            "displayName": display_name,
                            "description": description,
                            "database": entity.get("database", {}).get("displayName") if isinstance(entity.get("database"), dict) else None,
                            "service": entity.get("service", {}).get("displayName") if isinstance(entity.get("service"), dict) else None,
                            "tags": [t.get("tagFQN", "").split(".")[-1] for t in entity.get("tags", [])],
                            "columns": entity.get("columns", [])
                        }
                        
                        # Only add if missing description OR we're doing a describe task
                        # (We check _is_missing_description which returns False if desc exists)
                        if self._is_missing_description(description, entity_name=fqn):
                            undocumented.append(context)
                            logger.info(f"[_search_specific_table] Added to undocumented (missing desc): {fqn}")
                        else:
                            # Table HAS description - we still want to return it for describe tasks
                            # but mark it as NOT undocumented so the caller knows
                            logger.info(f"[_search_specific_table] Table has description, returning anyway: {fqn}")
                            # Return a single-element list with this table info
                            return [context]
                
                logger.info(f"_search_specific_table found {len(undocumented)} matching entities for '{table_name}'")
                
        except Exception as e:
            logger.warning(f"Error searching for specific table '{table_name}': {e}")
        
        return undocumented
    
    async def _gather_context(self, entity_fqn: str, mcp_client) -> Dict[str, Any]:
        """
        Step B - Gather detailed context for an entity.
        
        Args:
            entity_fqn: Fully qualified name of the entity
            mcp_client: MCP client for OpenMetadata
            
        Returns:
            Context dictionary with entity details
        """
        context = {
            "name": entity_fqn,
            "columns": [],
            "tags": [],
            "owner": None
        }
        
        try:
            async with mcp_client as client:
                details = await client.get_entity_details("table", entity_fqn)
                
                if details:
                    entity_data = details.get("entity", details)
                    context["displayName"] = entity_data.get("displayName", entity_fqn)
                    context["description"] = entity_data.get("description", "")
                    context["tags"] = [
                        t.get("tagFQN", "").split(".")[-1] 
                        for t in entity_data.get("tags", [])
                    ]
                    context["owner"] = entity_data.get("owner", {}).get("displayName")
                    
                    # Extract column information
                    columns = entity_data.get("columns", [])
                    context["columns"] = [
                        {
                            "name": col.get("name", ""),
                            "description": col.get("description", ""),
                            "dataType": col.get("dataType", "")
                        }
                        for col in columns[:20]  # Limit to first 20 columns
                    ]
                    
        except Exception as e:
            logger.warning(f"Error gathering context for {entity_fqn}: {e}")
        
        return context
    
    async def _generate_description(self, context: Dict[str, Any]) -> tuple[str, float]:
        """
        Step C - Generate a description via LLM.
        
        Args:
            context: Entity context dictionary
            
        Returns:
            Tuple of (generated_description, confidence)
        """
        llm = self._get_llm()
        
        # Build a prompt with the context
        column_list = ""
        if context.get("columns"):
            col_lines = []
            for col in context["columns"][:10]:
                col_desc = col.get("description", "No description")
                col_lines.append(f"  - {col.get('name')} ({col.get('dataType', 'unknown')}): {col_desc}")
            column_list = "\nColumns:\n" + "\n".join(col_lines)
        
        tags_str = ", ".join(context.get("tags", [])) if context.get("tags") else "None"
        column_names = ", ".join([c.get("name", "") for c in context.get("columns", [])[:5]])
        
        prompt = f"""You are a data documentation expert. Generate a single-sentence business description for this table.

Table name: {context.get('displayName', context.get('name', 'Unknown'))}
Database: {context.get('database', 'Unknown')}
Tags: {tags_str}
Columns: {column_names}

Rules:
- ONE sentence only
- Describe what kind of data this table likely contains based on its name and database
- Do NOT say "unavailable" or "unknown"
- Do NOT explain your reasoning
- Output ONLY the final description text

Example: "This table stores customer transaction records with product details and timestamps."

Your description:"""
        
        try:
            response = await llm.ainvoke(prompt)
            description = response.content if hasattr(response, 'content') else str(response)
            
            # Sanitize: strip chain-of-thought tokens before using LLM output
            description = strip_think(description)
            
            # Validate response
            description = description.strip()
            
            # Confidence 0.0 for "unavailable" or too-short descriptions
            if "unavailable" in description.lower() or len(description) < 15:
                return description, 0.0
            
            return description, 0.85
            
        except Exception as e:
            logger.warning(f"LLM description generation failed: {e}")
            return "Description generation failed.", 0.0
    
    async def execute(
        self, 
        task: str, 
        inputs: Dict[str, Any], 
        mcp_client: Any = None
    ) -> AgentFinding:
        """
        Execute the documentation workflow.
        
        Steps:
        A. Discover undocumented entities
        B. Gather context for each entity
        C. Generate descriptions via LLM
        D. Package findings with proposed actions
        
        Args:
            task: The specific task description
            inputs: Input data from blackboard (may include table_fqn list)
            mcp_client: MCP client for OpenMetadata
            
        Returns:
            AgentFinding with proposed description actions
        """
        logger.info(f"[DocumentationAgent] Executing task: {task}")
        logger.info(f"[DocumentationAgent] execute() called with inputs: {inputs}")
        logger.info(f"[DocumentationAgent] execute() called with task: {task[:100]}")

        # Check if this is an explanation/analysis task (vs documentation task)
        # BUT only if we have table_fqn from inputs - otherwise be more careful
        if self._is_explain_task(task) and inputs and inputs.get("table_fqn"):
            return await self._explain_nested_columns(task, inputs, mcp_client)
        
        # Log what we received in inputs
        table_list_from_inputs = inputs.get("table_list", []) if inputs else []
        logger.info(f"[DocumentationAgent] table_list from inputs has {len(table_list_from_inputs)} items")
        
        # Safety net: if no table_fqn from inputs but task mentions a specific entity, parse it
        if not inputs or (not inputs.get("table_fqn") and not inputs.get("entity_fqn")):
            logger.info("[DocumentationAgent] No table_fqn from previous agent, checking task for entity name...")
            # Try to extract entity name from task
            task_lower = task.lower()
            # Look for patterns like "describe openmetadata-table-bench" or "what is the big_table"
            for prefix in ["describe ", "what is ", "find the ", "what's "]:
                if prefix in task_lower:
                    potential_name = task_lower.split(prefix)[-1].strip()
                    # Clean up common suffixes
                    for suffix in [" table", " entity", " in the catalog", " in openmetadata"]:
                        if potential_name.endswith(suffix):
                            potential_name = potential_name[:-len(suffix)].strip()
                    if potential_name and len(potential_name) > 2:
                        logger.info(f"[DocumentationAgent] Extracted entity name from task: '{potential_name}'")
                        # Store as table_fqn so it gets used
                        if inputs is None:
                            inputs = {}
                        inputs["table_fqn"] = potential_name
                        break
        
        if mcp_client is None:
            mcp_client = get_mcp_client()
        
        task_lower = task.lower()
        database = inputs.get("database") if inputs else None
        if not database:
            database = self._extract_database_from_task(task)
        
        # Build search query from task and inputs context
        table_name = self._extract_table_name_from_task(task)
        if not table_name:
            table_name = inputs.get("entity_fqn") or inputs.get("table_fqn")
        
        undocumented = []
        proposed_actions = []
        details_results = []
        
        # Check if we have a list of tables from a previous agent
        table_list = inputs.get("table_list", []) if inputs else []
        logger.info(f"[DocumentationAgent] table_list has {len(table_list)} items from inputs")
        
        # Check for specific table name in task (FQN pattern with dots)
        specific_table = None
        import re
        # Look for FQN patterns like "database.schema.table" or "service.db.table"
        fqn_match = re.search(r'([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+){2,})', task)
        if fqn_match:
            specific_table = fqn_match.group(1)
        elif table_name and "." in table_name:
            specific_table = table_name
        
        # FIX: Check for table_fqn/entity_fqn/table_name in inputs and use it
        # The key may be any of these depending on what previous agent passed
        table_fqn = (
            inputs.get("table_fqn") or 
            inputs.get("entity_fqn") or 
            inputs.get("table_name") or 
            inputs.get("entity_name") or
            inputs.get("target_entity")
        ) if inputs else None
        
        logger.info(f"[DocumentationAgent] Received inputs: {inputs}")
        logger.info(f"[DocumentationAgent] Extracted table_fqn/entity_fqn: {table_fqn}")
        
        # Clean the table_fqn - remove extra text like " table in the OpenMetadata catalog"
        if table_fqn:
            raw_fqn = table_fqn
            # Remove common suffixes that get appended by other agents
            if raw_fqn.endswith(' table in the OpenMetadata catalog'):
                table_fqn = raw_fqn[:-len(' table in the OpenMetadata catalog')]
            elif raw_fqn.endswith(' entity in the OpenMetadata catalog'):
                table_fqn = raw_fqn[:-len(' entity in the OpenMetadata catalog')]
            elif raw_fqn.endswith(' in the OpenMetadata catalog'):
                table_fqn = raw_fqn[:-len(' in the OpenMetadata catalog')]
            table_fqn = ' '.join(table_fqn.split())
            
            logger.info(f"[DocumentationAgent] Cleaned table_fqn from '{raw_fqn}' to '{table_fqn}'")
        
        # If we have a specific table from inputs, use it directly
        if table_fqn:
            # Use the entity name or construct a search query
            specific_table = table_fqn
            logger.info(f"[DocumentationAgent] Using specific table from inputs: {specific_table}")
        
        try:
            # Step A - Discover undocumented entities
            if table_list:
                # Use tables provided by previous agent
                logger.info(f"[DocumentationAgent] Processing {len(table_list)} tables from input list")
                for table_fqn in table_list:
                    context = await self._gather_context(table_fqn, mcp_client)
                    if self._is_missing_description(context.get("description", "")):
                        undocumented.append(context)
                logger.info(f"[DocumentationAgent] Found {len(undocumented)} undocumented from table_list")
            elif specific_table:
                # Search for specific table by name (has dots = FQN pattern)
                logger.info(f"Searching for specific table: {specific_table}")
                undocumented = await self._search_specific_table(mcp_client, specific_table)
            else:
                # Build search query from context
                search_query = table_name or database or "table"
                undocumented = await self._discover_undocumented_entities(mcp_client, search_query)
            
            # Edge case: No undocumented entities but we have a specific table - return its info anyway
            if not undocumented and specific_table:
                # Try to get the table info even if it has description
                logger.info(f"[DocumentationAgent] Specific table '{specific_table}' found but may have description - gathering info anyway")
                try:
                    context = await self._gather_context(specific_table, mcp_client)
                    if context.get("name"):
                        # Return info about this table even if it has description
                        desc = context.get("description", "")
                        summary = f"Table: {context.get('displayName', specific_table)}"
                        if desc and desc != "FIELD_MISSING":
                            summary += f"\nDescription: {desc}"
                        else:
                            summary += "\nNo description available"
                        
                        # Get additional details
                        db = context.get("database", "")
                        service = context.get("service", "")
                        if db or service:
                            summary += f"\nDatabase: {db or 'N/A'}, Service: {service or 'N/A'}"
                        
                        return AgentFinding(
                            agent_id=self.agent_id,
                            subtask_id="describe_entity",
                            task_description=task,
                            finding_type="description",
                            target_entity=specific_table,
                            summary=summary,
                            details=context,
                            confidence=1.0,
                            proposed_actions=[],
                            mcp_tool_calls=[],
                            llm_reasoning=f"Found and described table: {specific_table}"
                        )
                except Exception as e:
                    logger.warning(f"[DocumentationAgent] Failed to gather context for {specific_table}: {e}")
            
            if not undocumented:
                return AgentFinding(
                    agent_id=self.agent_id,
                    subtask_id="document_entities",
                    task_description=task,
                    finding_type="description",
                    target_entity=None,
                    summary="No undocumented entities found",
                    details={"databases_searched": [database] if database else ["default"]},
                    confidence=1.0,  # Task completed successfully - nothing to document
                    proposed_actions=[],
                    mcp_tool_calls=[],
                    llm_reasoning="The documentation agent found no entities missing descriptions."
                )
            
            logger.info(f"Processing {len(undocumented)} undocumented entities")
            
            # Step B & C - Gather context and generate descriptions
            for entity in undocumented:
                try:
                    # Re-fetch context with full details
                    full_context = await self._gather_context(entity.get("name", ""), mcp_client)
                    
                    # Check if entity already has a description (describe use case)
                    existing_desc = full_context.get("description", "")
                    has_existing_desc = existing_desc and existing_desc != "FIELD_MISSING" and len(existing_desc) >= 10
                    
                    if has_existing_desc:
                        # Use existing description from catalog for describe tasks
                        logger.info(f"[DocumentationAgent] Found existing description for {entity.get('name')}: '{existing_desc[:80]}...'")
                        description = existing_desc
                        confidence = 1.0
                        
                        # Return immediately with a read-only finding (no action needed)
                        table_name = entity.get("displayName", entity.get("name", "Unknown"))
                        service = full_context.get("service", "Unknown")
                        db = full_context.get("database", "Unknown")
                        
                        return AgentFinding(
                            agent_id=self.agent_id,
                            subtask_id="describe_entity",
                            task_description=task,
                            finding_type="description",  # Use allowed value
                            target_entity=entity.get("name", ""),
                            summary=f"✅ Description for {table_name}: {description}",
                            details={
                                "fqn": entity.get("name", ""),
                                "displayName": table_name,
                                "description": description,
                                "service": service,
                                "database": db,
                                "tags": full_context.get("tags", []),
                                "columns": full_context.get("columns", [])[:10],  # Limit columns in details
                            },
                            confidence=1.0,
                            proposed_actions=[],  # NO action - description already exists!
                            mcp_tool_calls=[],
                            llm_reasoning="Retrieved existing description from OpenMetadata. No update required."
                        )
                    else:
                        # Generate description via LLM for undocumented entities
                        logger.info(f"[DocumentationAgent] Generating description for {entity.get('name')}")
                        description, confidence = await self._generate_description(full_context)
                    
                    if confidence > 0:
                        proposed_actions.append(ProposedAction(
                            action_type=ActionType.ADD_DESCRIPTION,
                            target_entity=entity.get("name", ""),
                            parameters={"description": description, "entity_type": "table"},
                            confidence=confidence,
                            proposed_by=self.agent_id
                        ))
                        
                        details_results.append({
                            "entity": entity.get("name", ""),
                            "displayName": entity.get("displayName", ""),
                            "generated_description": description,
                            "confidence": confidence
                        })
                        
                except Exception as e:
                    # Continue with other entities if one fails
                    logger.warning(f"Failed to process entity {entity.get('name', '')}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Documentation agent failed: {e}")
            return AgentFinding(
                agent_id=self.agent_id,
                subtask_id="document_entities",
                task_description=task,
                finding_type="description",
                target_entity=None,
                summary=f"Documentation agent failed: {str(e)}",
                details={"error": str(e)},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"An error occurred: {str(e)}"
            )
        
        # Calculate overall confidence based on successful generations
        overall_confidence = 0.0
        if details_results:
            overall_confidence = sum(r["confidence"] for r in details_results) / len(details_results)
        
        summary = f"Found {len(undocumented)} undocumented entities, generated descriptions for {len(details_results)}"
        
        # Debug logging for proposed_actions before return
        logger.info(f"[DocumentationAgent] RETURNING with {len(proposed_actions)} proposed_actions")
        for i, action in enumerate(proposed_actions):
            logger.info(f"  Action {i}: type={action.action_type}, target={action.target_entity}, params_keys={list(action.parameters.keys())}")
        
        return AgentFinding(
            agent_id=self.agent_id,
            subtask_id="document_entities",
            task_description=task,
            finding_type="description",
            target_entity=None,
            summary=summary,
            details={
                "undocumented_count": len(undocumented),
                "documented_count": len(details_results),
                "results": details_results,
                "database": database
            },
            confidence=overall_confidence,
            proposed_actions=proposed_actions,
            mcp_tool_calls=[],
            llm_reasoning=f"Documentation agent processed {len(undocumented)} entities and generated {len(details_results)} description proposals."
        )


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(DocumentationAgent())
