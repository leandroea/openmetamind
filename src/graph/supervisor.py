"""
Supervisor node for the OpenMetaMind swarm.

The Supervisor implements the Manager/Supervisor pattern for orchestrating
agent execution. Instead of parallel execution via Send API, the Supervisor
executes agents sequentially and synthesizes results.

Supervisor Loop:
1. Check if there are pending tasks
2. If yes, execute next task and loop
3. If no, move to integrity critic
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from ..models.state import SwarmState, AgentFinding, FindingType
from ..models.plan import Subtask
from ..agents.registry import AgentRegistry
from ..mcp.client import get_mcp_client

logger = logging.getLogger(__name__)


class Supervisor:
    """
    The Supervisor node in the LangGraph workflow.
    
    Responsibilities:
    - Execute tasks sequentially from the pending task queue
    - Call appropriate agents for each task
    - Synthesize results after each agent completes
    - Manage the execution loop until all tasks are done
    """

    def __init__(self):
        """Initialize the Supervisor."""
        pass

    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute the Supervisor node.
        
        Main supervisor logic:
        1. Check if there are pending tasks
        2. If yes, execute next task and return to supervisor loop
        3. If no, move to integrity critic
        
        Args:
            state: Current swarm state containing pending_tasks
            
        Returns:
            Dictionary with state updates and routing decision
        """
        pending_tasks = state.get("pending_tasks", [])
        
        if not pending_tasks:
            # All tasks completed - move to critic
            logger.info("Supervisor: No pending tasks, moving to integrity_critic")
            return {"next": "integrity_critic"}
        
        # Get current task (first in queue)
        current_task = pending_tasks[0]
        subtask_id = current_task.get("subtask_id") if isinstance(current_task, dict) else current_task.subtask_id
        agent_id = current_task.get("agent_id") if isinstance(current_task, dict) else current_task.agent_id
        
        logger.info(f"Supervisor: Executing task {subtask_id} with agent {agent_id}")
        
        # Execute the agent
        finding = self._execute_agent_sync(current_task, state)
        
        # Prepare agent_id for status update
        agent_id_for_status = current_task.get("agent_id") if isinstance(current_task, dict) else current_task.agent_id
        
        # Update state with results
        new_findings = state.get("findings", []) + [finding]
        new_completed = state.get("completed_subtasks", []) + [subtask_id]
        remaining_tasks = pending_tasks[1:]
        
        if remaining_tasks:
            # More tasks to do - stay in supervisor loop
            logger.info(f"Supervisor: Task {subtask_id} completed, {len(remaining_tasks)} tasks remaining")
            return {
                "findings": new_findings,
                "completed_subtasks": new_completed,
                "pending_tasks": remaining_tasks,
                "agent_statuses": {agent_id_for_status: "completed"},
                "next": "supervisor"
            }
        else:
            # All done - move to critic
            logger.info(f"Supervisor: All tasks completed, moving to integrity_critic")
            return {
                "findings": new_findings,
                "completed_subtasks": new_completed,
                "pending_tasks": [],
                "agent_statuses": {agent_id_for_status: "completed"},
                "next": "integrity_critic"
            }

    def _execute_agent_sync(self, task: Any, state: SwarmState) -> AgentFinding:
        """
        Synchronous wrapper for async agent execution.
        
        Args:
            task: The task to execute (Subtask or dict)
            state: Current swarm state
            
        Returns:
            AgentFinding from the agent execution
        """
        # Prepare inputs from blackboard
        inputs = self._prepare_inputs(task, state)
        
        # Get task details
        task_description = task.get("task") if isinstance(task, dict) else task.task_description
        agent_id = task.get("agent_id") if isinstance(task, dict) else task.agent_id
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            finding = loop.run_until_complete(
                self._execute_agent_async(agent_id, task_description, inputs)
            )
            return finding
        finally:
            loop.close()

    async def _execute_agent_async(self, agent_id: str, task_description: str, inputs: Dict[str, Any]) -> AgentFinding:
        """
        Execute agent with MCP client.
        
        Args:
            agent_id: ID of the agent to execute
            task_description: Natural language description of the task
            inputs: Input data from blackboard
            
        Returns:
            AgentFinding from the agent execution
        """
        # Get agent from registry
        registry = AgentRegistry()
        agent = registry.get_agent(agent_id)
        
        if not agent:
            logger.error(f"Supervisor: Agent {agent_id} not found in registry")
            return self._create_error_finding(
                agent_id=agent_id,
                subtask_id="unknown",
                task_description=task_description,
                error_msg=f"Agent {agent_id} not found in registry"
            )
        
        # Execute with MCP client
        mcp_client = get_mcp_client()
        try:
            async with mcp_client as client:
                logger.info(f"[Supervisor] Passing inputs to {agent_id}: {inputs}")
                logger.info(f"[Supervisor] Task description: {task_description[:100] if task_description else 'None'}")
                finding = await agent.execute(
                    task=task_description,
                    inputs=inputs,
                    mcp_client=client
                )
                logger.info(f"Supervisor: Agent {agent_id} completed with confidence {finding.confidence}")
                return finding
        except Exception as e:
            logger.error(f"Supervisor: Agent {agent_id} failed: {str(e)}", exc_info=True)
            return self._create_error_finding(
                agent_id=agent_id,
                subtask_id="unknown",
                task_description=task_description,
                error_msg=str(e)
            )

    def _prepare_inputs(self, task: Any, state: SwarmState) -> Dict[str, Any]:
        """
        Prepare inputs for agent from blackboard.
        
        Args:
            task: The task to prepare inputs for
            state: Current swarm state
            
        Returns:
            Dictionary of inputs for the agent
        """
        blackboard = state.get("blackboard", {})
        # Check both blackboard.findings and state.findings (top-level)
        findings = blackboard.get("findings", []) or state.get("findings", [])
        required_inputs = task.get("required_inputs", []) if isinstance(task, dict) else getattr(task, 'required_inputs', [])
        
        logger.info(f"[_prepare_inputs] required_inputs: {required_inputs}")
        logger.info(f"[_prepare_inputs] blackboard findings count: {len(blackboard.get('findings', []))}")
        logger.info(f"[_prepare_inputs] state findings count: {len(state.get('findings', []))}")
        
        inputs = {}
        for key in required_inputs:
            # Check blackboard first
            if key in blackboard:
                inputs[key] = blackboard[key]
            
            # Special handling for table_fqn - extract from previous finding's target_entity or details
            if key == "table_fqn" and key not in inputs and findings:
                # Get the most recent finding with a target_entity or details.entities
                for finding in reversed(findings):
                    logger.info(f"[_prepare_inputs] Checking finding: agent={getattr(finding, 'agent_id', '?')}, target={getattr(finding, 'target_entity', 'None')}")
                    if hasattr(finding, 'target_entity') and finding.target_entity:
                        inputs[key] = finding.target_entity
                        logger.info(f"Supervisor: Extracted table_fqn='{finding.target_entity}' from previous finding's target_entity")
                        break
                    # Also check details.entities for FQN
                    if hasattr(finding, 'details') and isinstance(finding.details, dict):
                        entities = finding.details.get("entities", [])
                        if entities and len(entities) > 0:
                            first_entity = entities[0]
                            if isinstance(first_entity, dict) and first_entity.get("fullyQualifiedName"):
                                inputs[key] = first_entity["fullyQualifiedName"]
                                logger.info(f"Supervisor: Extracted table_fqn='{first_entity['fullyQualifiedName']}' from previous finding's details.entities")
                                break
        
        return inputs

    def _create_error_finding(
        self,
        agent_id: str,
        subtask_id: str,
        task_description: str,
        error_msg: str
    ) -> AgentFinding:
        """
        Create error finding when agent fails.
        
        Args:
            agent_id: ID of the agent
            subtask_id: ID of the subtask
            task_description: Description of the task
            error_msg: Error message
            
        Returns:
            AgentFinding with error information
        """
        return AgentFinding(
            agent_id=agent_id,
            subtask_id=subtask_id,
            task_description=task_description,
            finding_type=FindingType.OTHER,
            summary=f"Task failed: {error_msg}",
            details={"error": error_msg},
            confidence=0.0,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning=f"Agent {agent_id} failed during execution: {error_msg}"
        )


# Singleton instance for use in the graph
supervisor = Supervisor()
