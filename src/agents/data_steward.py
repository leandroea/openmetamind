"""
Data Steward Agent - Classifies data and manages governance.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional

from .base import SwarmAgent, Capability
from ..models.state import AgentFinding, ProposedAction, ActionType
from ..mcp.client import get_mcp_client, OpenMetadataMCPClient

# LangChain imports for MiniMax LLM (OpenAI-compatible API)
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("LangChain not available. Data Steward will use regex-only PII detection.")

logger = logging.getLogger(__name__)

class DataSteward(SwarmAgent):
    """Handles data classification, PII detection, tag assignment, and ownership management."""

    agent_id = "data_steward"
    display_name = "Data Steward"
    description = "Handles data classification, PII detection, tag assignment, and ownership management"
    avatar_emoji = "🛡️"

    capabilities = [
        Capability(
            name="pii_detection",
            description="Detects personally identifiable information in columns",
            input_schema={"table_fqn": "string"},
            output_schema={"pii_columns": "list[ColumnClassification]"}
        ),
        Capability(
            name="tag_assignment",
            description="Assigns governance tags to entities",
            input_schema={"entity_fqn": "string", "proposed_tags": "list[string]"},
            output_schema={"assigned_tags": "list[string]", "rejected_tags": "list[string]"}
        ),
        Capability(
            name="ownership_management",
            description="Suggests or assigns asset owners",
            input_schema={"entity_fqn": "string"},
            output_schema={"proposed_owner": "string", "confidence": "float"}
        )
    ]

    def __init__(self):
        """Initialize the Data Steward with MiniMax LLM if available."""
        super().__init__()
        self.llm = None
        if LANGCHAIN_AVAILABLE:
            try:
                # Initialize ChatOpenAI with MiniMax endpoint
                import os
                minimax_api_key = os.getenv("MINIMAX_API_KEY")
                if not minimax_api_key:
                    logger.warning("MINIMAX_API_KEY not found in environment variables. Data Steward will use regex-only PII detection.")
                else:
                    # Initialize ChatOpenAI with MiniMax endpoint
                    self.llm = ChatOpenAI(
                        base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
                        api_key=minimax_api_key,
                        model=os.getenv("LLM_MODEL", "minimax-m2.7"),
                        temperature=0.1,
                        max_tokens=1000
                    )
                    logger.info("Data Steward initialized with MiniMax LLM")
            except Exception as e:
                logger.warning(f"Failed to initialize MiniMax LLM: {e}. Falling back to regex-only.")
                self.llm = None

    async def can_handle(self, task_description: str) -> float:
        """
        Determine if this agent can handle the task based on keywords.
        """
        task_lower = task_description.lower()
        stewardship_keywords = [
            "classify", "classification", "pii", "sensitive", "tag", "tagging",
            "owner", "ownership", "steward", "governance", "policy", "compliance",
            "detect", "identify", "label", "categorize"
        ]

        score = 0.0
        for keyword in stewardship_keywords:
            if keyword in task_lower:
                score += 0.15

        # Cap the score at 1.0
        return min(score, 1.0)

    async def execute(
        self,
        task: str,
        inputs: Dict[str, Any],
        mcp_client: Any = None
    ) -> AgentFinding:
        """
        Execute the data steward's classification logic.

        Args:
            task: The specific task description for this agent
            inputs: Dictionary of input data from the blackboard
            mcp_client: MCP client for interacting with OpenMetadata

        Returns:
            AgentFinding containing classification results and proposed actions
        """
        logger.info(f"[DataSteward] Executing task: {task}")
        
        # Get MCP client if not provided
        if mcp_client is None:
            mcp_client = get_mcp_client()

        # Determine what entity to work on from inputs or task
        entity_fqn = None
        if inputs and "entity_fqn" in inputs:
            entity_fqn = inputs["entity_fqn"]
        elif inputs and "table_fqn" in inputs:
            entity_fqn = inputs["table_fqn"]

        # Extract entity FQN from task if not in inputs
        if not entity_fqn:
            # Simple regex to extract FQN-like patterns from task
            fqn_pattern = r'[a-zA-Z0-9_.]+\.[a-zA-Z0-9_.]+\.[a-zA-Z0-9_.]+'
            matches = re.findall(fqn_pattern, task)
            if matches:
                entity_fqn = matches[0]

        # If we still don't have an entity, we can't do much
        if not entity_fqn:
            finding = AgentFinding(
                agent_id=self.agent_id,
                subtask_id="data_steward",
                task_description=task,
                finding_type="classification",
                summary="Data Steward: No entity specified for classification",
                details={"error": "No entity FQN provided in task or inputs"},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning="Cannot perform data stewardship without a target entity."
            )
            return finding

        try:
            # Use the MCP client to get entity details (column info) using available tool
            async with mcp_client as client:
                # Get entity details which includes column information
                entity_details = await client.get_entity_details(
                    entity_type="table",
                    fqn=entity_fqn
                )
                
                # Perform PII detection on columns using entity details
                pii_results = self._detect_pii_from_columns(entity_fqn, entity_details)

                # Generate proposed actions based on findings
                proposed_actions = []

                # Add tag assignment actions for PII columns
                if pii_results:
                    pii_column_names = [col["column_name"] for col in pii_results if col["is_pii"]]
                    if pii_column_names:
                        # Suggest PII tag for columns with PII
                        action = ProposedAction(
                            action_type=ActionType.ASSIGN_TAG,
                            target_entity=entity_fqn,
                            parameters={
                                "tags": ["PII"],
                                "column_names": pii_column_names # Assuming MCP supports column-level tagging
                            },
                            confidence=0.9,
                            proposed_by=self.agent_id
                        )
                        proposed_actions.append(action)

                # Create summary
                pii_count = len([col for col in pii_results if col["is_pii"]]) if pii_results else 0
                total_columns = len(pii_results) if pii_results else 0
                summary = f"Data Steward analyzed {total_columns} columns, found {pii_count} with potential PII"

                # Create details
                details = {
                    "entity_fqn": entity_fqn,
                    "entity_details": entity_details if isinstance(entity_details, dict) else {"raw": str(entity_details)},
                    "column_analysis": pii_results,
                    "pii_count": pii_count,
                    "total_columns": total_columns
                }

                # Create finding
                finding = AgentFinding(
                    agent_id=self.agent_id,
                    subtask_id="data_classification",
                    task_description=task,
                    finding_type="classification",
                    target_entity=entity_fqn,
                    summary=summary,
                    details=details,
                    confidence=0.85 if pii_results else 0.7,
                    proposed_actions=proposed_actions,
                    mcp_tool_calls=[], # Would be populated by MCP client internally
                    llm_reasoning=f"The Data Steward analyzed table {entity_fqn} for PII using {'LLM-assisted' if self.llm else 'regex-based'} detection."
                )

                return finding

        except Exception as e:
            logger.error(f"Data Steward failed: {str(e)}")
            # Return a finding indicating failure
            finding = AgentFinding(
                agent_id=self.agent_id,
                subtask_id="data_classification",
                task_description=task,
                finding_type="other",
                summary=f"Data Steward failed: {str(e)}",
                details={"error": str(e), "entity_fqn": entity_fqn},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"An error occurred while performing data stewardship: {str(e)}"
            )
            return finding

    def _detect_pii_from_columns(
        self,
        table_fqn: str,
        entity_details: Any
    ) -> List[Dict[str, Any]]:
        """
        Detect PII in columns from entity details (available MCP tool data).

        Args:
            table_fqn: Fully qualified name of the table
            entity_details: Entity details dict from get_entity_details

        Returns:
            List of column analysis results
        """
        pii_results = []
        
        if isinstance(entity_details, dict):
            columns = entity_details.get('columns', [])
        else:
            columns = []
        
        if not columns:
            return pii_results
        
        # PII detection patterns
        pii_patterns = {
            'email': ['email', 'mail', 'e-mail'],
            'phone': ['phone', 'tel', 'mobile', 'cell', 'fax'],
            'ssn': ['ssn', 'social_security', 'national_id'],
            'credit_card': ['credit', 'card', 'cc_', 'visa', 'mastercard'],
            'password': ['password', 'pwd', 'secret', 'token', 'api_key'],
            'address': ['address', 'street', 'city', 'zip', 'postal', 'country'],
            'name': ['name', 'first_name', 'last_name', 'full_name', 'surname'],
            'date': ['birth', 'dob', 'birthday', 'date_of_birth', 'birthdate'],
            'ip': ['ip_address', 'ip', 'mac_address'],
        }
        
        for col in columns:
            col_name = col.get('name', '')
            col_name_lower = col_name.lower()
            data_type = col.get('dataType', col.get('data_type', 'unknown'))
            description = col.get('description', '')
            
            # Check for PII patterns
            detected_pii_type = None
            for pii_type, keywords in pii_patterns.items():
                for keyword in keywords:
                    if keyword in col_name_lower:
                        detected_pii_type = pii_type
                        break
                if detected_pii_type:
                    break
            
            # Use LLM for additional analysis if available and column has description
            if detected_pii_type is None and self.llm and description:
                # Could enhance with LLM here, but for now skip
                pass
            
            if detected_pii_type:
                pii_results.append({
                    "column_name": col_name,
                    "data_type": data_type,
                    "is_pii": True,
                    "pii_type": detected_pii_type,
                    "confidence": 0.9,
                    "reasoning": f"Column name '{col_name}' matches {detected_pii_type} pattern"
                })
            else:
                pii_results.append({
                    "column_name": col_name,
                    "data_type": data_type,
                    "is_pii": False,
                    "pii_type": None,
                    "confidence": 0.7,
                    "reasoning": "No PII indicators detected in column name"
                })
        
        return pii_results

# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(DataSteward())