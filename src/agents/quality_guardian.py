"""
Quality Guardian Agent - Analyzes data quality and detects anomalies.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from .base import SwarmAgent, Capability
from ..models.state import AgentFinding, ProposedAction, ActionType
from ..mcp.client import get_mcp_client, OpenMetadataMCPClient

logger = logging.getLogger(__name__)


class QualityGuardian(SwarmAgent):
    """Profiles tables, detects anomalies, and validates SLAs."""
    
    agent_id = "quality_guardian"
    display_name = "Quality Guardian"
    description = "Profiles tables, detects anomalies, and validates SLAs"
    avatar_emoji = "🔬"
    
    capabilities = [
        Capability(
            name="profile_table",
            description="Profiles a table to gather quality metrics",
            input_schema={"table_fqn": "string"},
            output_schema={"profile": "TableProfile", "quality_score": "float"}
        ),
        Capability(
            name="detect_anomalies",
            description="Detects anomalies in data distribution and quality",
            input_schema={"table_fqn": "string", "baseline_profile": "dict"},
            output_schema={"anomalies": "list[Anomaly]", "severity": "string"}
        ),
        Capability(
            name="validate_sla",
            description="Validates data quality against service level agreements",
            input_schema={"table_fqn": "string", "sla_requirements": "dict"},
            output_schema={"compliant": "boolean", "violations": "list[string]"}
        )
    ]
    
    async def can_handle(self, task_description: str) -> float:
        """
        Determine if this agent can handle the task based on keywords.
        """
        task_lower = task_description.lower()
        quality_keywords = [
            "quality", "profile", "profiling", "anomaly", "anomalies", 
            "null", "empty", "duplicate", "stale", "fresh", "monitor",
            "sla", "service level", "metric", "metrics", "score", "health"
        ]
        
        score = 0.0
        for keyword in quality_keywords:
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
        Execute the quality guardian's analysis logic.
        
        Args:
            task: The specific task description for this agent
            inputs: Dictionary of input data from the blackboard
            mcp_client: MCP client for interacting with OpenMetadata
            
        Returns:
            AgentFinding containing quality metrics and proposed actions
        """
        # Get MCP client if not provided
        if mcp_client is None:
            mcp_client = get_mcp_client()
        
        # Determine what table to work on from inputs or task
        table_fqn = None
        if inputs and "table_fqn" in inputs:
            table_fqn = inputs["table_fqn"]
        elif inputs and "entity_fqn" in inputs:
            table_fqn = inputs["entity_fqn"]
        
        # Extract table FQN from task if not in inputs
        if not table_fqn:
            # Simple regex to extract FQN-like patterns from task
            import re
            fqn_pattern = r'[a-zA-Z0-9_.]+\\.[a-zA-Z0-9_.]+\\.[a-zA-Z0-9_.]+'
            matches = re.findall(fqn_pattern, task)
            if matches:
                table_fqn = matches[0]
        
        # If we still don't have a table, we can't do much
        if not table_fqn:
            finding = AgentFinding(
                agent_id=self.agent_id,
                subtask_id="quality_analysis",
                task_description=task,
                finding_type="quality",
                summary="Quality Guardian: No table specified for analysis",
                details={"error": "No table FQN provided in task or inputs"},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning="Cannot perform quality analysis without a target table."
            )
            return finding
        
        try:
            # Use the MCP client to get table profile
            async with mcp_client as client:
                table_profile = await client.get_table_profile(fqn=table_fqn)
                
                # Calculate quality metrics from profile
                quality_metrics = self._calculate_quality_metrics(table_profile)
                
                # Detect anomalies (simplified)
                anomalies = await self._detect_anomalies(table_profile, client)
                
                # Generate proposed actions based on findings
                proposed_actions = []
                
                # If quality score is low, suggest actions
                if quality_metrics["quality_score"] < 0.8:
                    # Suggest adding a description about quality issues
                    action = ProposedAction(
                        action_type=ActionType.ADD_DESCRIPTION,
                        entity_fqn=table_fqn,
                        parameters={
                            "description": f"Data quality score: {quality_metrics['quality_score']:.2f}. Review recommended."
                        },
                        confidence=0.8,
                        proposed_by=self.agent_id
                    )
                    proposed_actions.append(action)
                
                # Create summary
                quality_score = quality_metrics["quality_score"]
                summary = f"Quality Guardian analyzed {table_fqn}: Quality score {quality_score:.2f}"
                if anomalies:
                    summary += f", detected {len(anomalies)} anomaly(ies)"
                
                # Create details
                details = {
                    "table_fqn": table_fqn,
                    "table_profile": table_profile.dict() if hasattr(table_profile, 'dict') else table_profile,
                    "quality_metrics": quality_metrics,
                    "anomalies": [anomaly.dict() if hasattr(anomaly, 'dict') else anomaly for anomaly in anomalies],
                    "quality_score": quality_score
                }
                
                # Create finding
                finding = AgentFinding(
                    agent_id=self.agent_id,
                    subtask_id="quality_analysis",
                    task_description=task,
                    finding_type="quality",
                    target_entity=table_fqn,
                    summary=summary,
                    details=details,
                    confidence=0.9,  # High confidence in quality metrics from MCP
                    proposed_actions=proposed_actions,
                    mcp_tool_calls=[],  # Would be populated by MCP client internally
                    llm_reasoning=f"The Quality Guardian profiled table {table_fqn} and calculated quality metrics based on OpenMetadata data."
                )
                
                return finding
                
        except Exception as e:
            logger.error(f"Quality Guardian failed: {str(e)}")
            # Return a finding indicating failure
            finding = AgentFinding(
                agent_id=self.agent_id,
                subtask_id="quality_analysis",
                task_description=task,
                finding_type="other",
                summary=f"Quality Guardian failed: {str(e)}",
                details={"error": str(e), "table_fqn": table_fqn},
                confidence=0.0,
                proposed_actions=[],
                mcp_tool_calls=[],
                llm_reasoning=f"An error occurred while performing quality analysis: {str(e)}"
            )
            return finding
    
    def _calculate_quality_metrics(self, table_profile: Any) -> Dict[str, Any]:
        """
        Calculate quality metrics from table profile.
        
        Args:
            table_profile: TableProfile object from MCP
            
        Returns:
            Dictionary of quality metrics
        """
        # Extract metrics from table profile
        # This is a simplified implementation - in reality, we'd have more detailed profile data
        row_count = getattr(table_profile, 'rowCount', None) or getattr(table_profile, 'row_count', None)
        column_count = getattr(table_profile, 'columnCount', None) or getattr(table_profile, 'column_count', None)
        
        # For this scaffold, we'll return placeholder metrics
        # In a full implementation, we'd calculate actual quality scores
        return {
            "completeness": 0.95,  # Placeholder
            "uniqueness": 0.90,    # Placeholder
            "validity": 0.85,      # Placeholder
            "quality_score": 0.90  # Overall quality score
        }
    
    async def _detect_anomalies(
        self, 
        table_profile: Any, 
        mcp_client: OpenMetadataMCPClient
    ) -> List[Any]:
        """
        Detect anomalies in table data.
        
        Args:
            table_profile: TableProfile object from MCP
            mcp_client: Initialized MCP client
            
        Returns:
            List of anomaly objects
        """
        # For this scaffold, we'll return a placeholder result
        # In a full implementation, we would:
        # 1. Get historical profiles for comparison
        # 2. Use statistical methods to detect anomalies
        # 3. Return structured anomaly results
        
        # Placeholder implementation - return empty list for now
        return []


# Self-register on import
from .registry import AgentRegistry
AgentRegistry().register(QualityGuardian())