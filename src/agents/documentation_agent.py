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
                max_tokens=500
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
    
    def _is_missing_description(self, description: str) -> bool:
        """
        Check if a description is missing or too short to be useful.
        A description is considered missing if:
        - It is None, empty, or whitespace-only
        - It is shorter than 10 characters (too short to be useful)
        """
        if not description:
            return True
        if len(description.strip()) < 10:
            return True
        return False
    
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
            
        Returns:
            List of undocumented entities with their context
        """
        undocumented = []
        
        try:
            async with mcp_client as client:
                # Search for tables
                query = search_query if search_query else "table"
                search_result = await client.search_metadata_all(
                    query=query,
                    entity_type="table",
                    max_results=100
                )
                
                entities = search_result.get("results", [])
                
                for entity in entities:
                    name = entity.get("fullyQualifiedName", entity.get("name", ""))
                    description = entity.get("description", "")
                    
                    if self._is_missing_description(description):
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
                
                logger.info(f"Found {len(undocumented)} undocumented entities")
                
        except Exception as e:
            logger.error(f"Error discovering undocumented entities: {e}")
        
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
        
        prompt = f"""Generate a single-sentence, business-friendly description for this table:

Table: {context.get('displayName', context.get('name', 'Unknown'))}
Tags: {tags_str}
Owner: {context.get('owner', 'Unknown') or 'Unknown'}{column_list}

Respond with ONLY the description text, no preamble or formatting. Be concise and specific about what business data this table contains. If there's insufficient information, respond with "Description unavailable." """

        try:
            response = await llm.ainvoke(prompt)
            description = response.content if hasattr(response, 'content') else str(response)
            
            # Validate response
            description = description.strip()
            if len(description) < 10 or "unavailable" in description.lower():
                return description, 0.3
            
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
        
        try:
            # Step A - Discover undocumented entities
            if table_list:
                # Use tables provided by previous agent
                for table_fqn in table_list:
                    context = await self._gather_context(table_fqn, mcp_client)
                    if self._is_missing_description(context.get("description", "")):
                        undocumented.append(context)
            else:
                # Build search query from context
                search_query = table_name or database or "table"
                undocumented = await self._discover_undocumented_entities(mcp_client, search_query)
            
            # Edge case: No undocumented entities
            if not undocumented:
                return AgentFinding(
                    agent_id=self.agent_id,
                    subtask_id="document_entities",
                    task_description=task,
                    finding_type="description",
                    target_entity=None,
                    summary="No undocumented entities found",
                    details={"databases_searched": [database] if database else ["default"]},
                    confidence=0.0,
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
                    
                    # Generate description
                    description, confidence = await self._generate_description(full_context)
                    
                    if confidence > 0:
                        proposed_actions.append(ProposedAction(
                            action_type=ActionType.ADD_DESCRIPTION,
                            entity_fqn=entity.get("name", ""),
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
