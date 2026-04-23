"""
Action Executor node for the OpenMetaMind swarm.

Performs actual MCP write operations. The only component with write permissions.
"""

import asyncio
import logging
from typing import List, Dict, Any, Set

from ..models.state import SwarmState, ProposedAction, ActionType
from ..mcp.client import get_mcp_client, OpenMetadataMCPClient

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    The Action Executor in the OpenMetaMind swarm.
    
    Responsibilities:
    - Performs actual MCP write operations
    - Only component with write permissions
    - Batched, idempotent execution
    - Respects fail_fast configuration
    """

    def __init__(self, fail_fast: bool = True):
        """Initialize the Action Executor."""
        self.fail_fast = fail_fast

    async def execute_batch(
        self, 
        actions: List[ProposedAction], 
        executed_actions: Set[str],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute approved actions via MCP with idempotency checking.
        
        Args:
            actions: List of approved actions to execute
            executed_actions: Set of action hashes already executed (for idempotency)
            dry_run: If True, only validate without executing
            
        Returns:
            Dictionary with execution results
        """
        results = []
        newly_executed = set()  # Track newly executed actions in this batch
        
        for action in actions:
            # Check idempotency: skip if already executed
            action_hash = self._get_action_hash(action)
            if action_hash in executed_actions:
                logger.info(f"Skipping already executed action: {action.action_type} on {action.entity_fqn}")
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": True,
                    "result": {"message": "Already executed (idempotency skip)"},
                    "skipped": True
                })
                continue
            
            # Check if we've already executed this action in this batch (double-check)
            if action_hash in newly_executed:
                logger.info(f"Skipping duplicate action in batch: {action.action_type} on {action.entity_fqn}")
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": True,
                    "result": {"message": "Already executed in this batch (idempotency skip)"},
                    "skipped": True
                })
                continue
            
            try:
                if dry_run:
                    # In dry-run mode, we still want to validate the action would work
                    # For now, we'll simulate but log what we would do
                    logger.info(f"DRY RUN: Would execute {action.action_type} on {action.entity_fqn}")
                    result = await self._validate_action(action)
                else:
                    # Actually execute the MCP call
                    result = await self._execute_mcp(action)
                
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": True,
                    "result": result
                })
                
                # Mark as executed only if successful
                newly_executed.add(action_hash)
                
                # If fail_fast is True and we had a failure, we would have raised an exception
                # Since we're continuing, we just keep track of successes
                
            except Exception as e:
                logger.error(f"Action execution failed: {action.action_type} on {action.entity_fqn}: {str(e)}")
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": False,
                    "error": str(e)
                })
                
                # Stop on first failure if fail_fast is True
                if self.fail_fast:
                    logger.info("Fail-fast enabled, stopping execution after first failure")
                    break
                # Otherwise continue with other actions
        
        # Return results and the set of newly executed actions for state update
        return {
            "results": results,
            "total_actions": len(actions),
            "successful_actions": len([r for r in results if r.get("success", False)]),
            "failed_actions": len([r for r in results if not r.get("success", True)]),
            "dry_run": dry_run,
            "newly_executed": newly_executed  # These need to be added to executed_actions in state
        }
    
    async def _execute_mcp(self, action: ProposedAction) -> Dict[str, Any]:
        """
        Map ProposedAction to REAL MCP tool call.
        
        Args:
            action: The action to execute
            
        Returns:
            Result from MCP tool call
        """
        # Get MCP client
        mcp_client = get_mcp_client()
        
        # Map action type to MCP tool name
        tool_map = {
            ActionType.ASSIGN_TAG: "add_tags",
            ActionType.UPDATE_OWNER: "update_owner",
            ActionType.ADD_DESCRIPTION: "update_description",
            ActionType.CREATE_GLOSSARY_TERM: "create_glossary_term",
            ActionType.UPDATE_LINEAGE: "update_lineage",
            ActionType.ADD_OWNER: "add_owner",
            ActionType.REMOVE_OWNER: "remove_owner",
            ActionType.DELETE_TAG: "delete_tag",
            # Add more mappings as needed
        }
        
        tool_name = tool_map.get(action.action_type)
        if not tool_name:
            raise ValueError(f"No MCP tool mapping for action type: {action.action_type}")
        
        # Execute the REAL MCP tool call
        async with mcp_client as client:
            result = await client._call_mcp_tool(tool_name, action.parameters)
            return result
    
    async def _validate_action(self, action: ProposedAction) -> Dict[str, Any]:
        """
        Validate an action for dry-run mode.
        In a real implementation, this might do a dry-run call to MCP if supported.
        
        Args:
            action: The action to validate
            
        Returns:
            Validation result
        """
        # For dry-run, we check if the action is well-formed
        # In a full implementation, we might make a dry-run MCP call if the API supports it
        return {
            "dry_run": True,
            "action_type": action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type),
            "entity_fqn": action.entity_fqn,
            "parameters": action.parameters,
            "message": f"DRY RUN: Validated {action.action_type} on {action.entity_fqn} - would execute in live mode"
        }
    
    def _get_action_hash(self, action: ProposedAction) -> str:
        """
        Generate a hash for an action to check idempotency.
        
        Args:
            action: The action to hash
            
        Returns:
            String hash representing the action
        """
        # Simple hash based on action type, entity, and parameters
        import hashlib
        action_str = f"{action.action_type}:{action.entity_fqn}:{str(sorted(action.parameters.items()))}"
        return hashlib.md5(action_str.encode()).hexdigest()


# Node function for LangGraph (expects synchronous function)
def action_executor_node(state: SwarmState) -> Dict[str, Any]:
    """
    Action Executor node for LangGraph workflow.
    
    Args:
        state: Current swarm state containing approved_actions and executed_actions
        
    Returns:
        Dictionary with state updates
    """
    approved_actions = state.get("approved_actions", [])
    executed_actions = set(state.get("executed_actions", []))  # Get from state, default to empty set
    
    if not approved_actions:
        return {
            "action_results": {
                "total_actions": 0,
                "successful_actions": 0,
                "failed_actions": 0,
                "results": []
            },
            "executed_actions": list(executed_actions)  # Return as list for JSON serialization
        }
    
    # Convert dicts to ProposedAction objects if needed
    actions = []
    for action_dict in approved_actions:
        if isinstance(action_dict, dict):
            actions.append(ProposedAction(**action_dict))
        else:
            actions.append(action_dict)
    
    # Create executor and run batch
    executor = ActionExecutor(fail_fast=True)  # Could make this configurable
    
    # Run async function in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            executor.execute_batch(actions, executed_actions, dry_run=False)
        )
    finally:
        loop.close()
    
    # Update executed_actions in state
    updated_executed_actions = executed_actions.union(result.get("newly_executed", set()))
    
    return {
        "action_results": {
            "results": result["results"],
            "total_actions": result["total_actions"],
            "successful_actions": result["successful_actions"],
            "failed_actions": result["failed_actions"],
            "dry_run": result["dry_run"]
        },
        "executed_actions": list(updated_executed_actions),  # Store as list in state
        # Clear approved actions after execution to prevent re-execution
        "approved_actions": []
    }


# Dry-run node for testing
def action_executor_dry_run_node(state: SwarmState) -> Dict[str, Any]:
    """
    Dry-run version of the Action Executor for testing.
    
    Args:
        state: Current swarm state containing approved_actions
        
    Returns:
        Dictionary with state updates
    """
    approved_actions = state.get("approved_actions", [])
    executed_actions = set(state.get("executed_actions", []))  # Get from state
    
    if not approved_actions:
        return {
            "action_results": {
                "total_actions": 0,
                "successful_actions": 0,
                "failed_actions": 0,
                "results": []
            },
            "executed_actions": list(executed_actions)
        }
    
    # Convert dicts to ProposedAction objects if needed
    actions = []
    for action_dict in approved_actions:
        if isinstance(action_dict, dict):
            actions.append(ProposedAction(**action_dict))
        else:
            actions.append(action_dict)
    
    # Create executor and run batch in dry-run mode
    executor = ActionExecutor(fail_fast=True)
    
    # Run async function in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            executor.execute_batch(actions, executed_actions, dry_run=True)
        )
    finally:
        loop.close()
    
    # In dry-run, we don't update executed_actions since nothing was actually executed
    return {
        "action_results": {
            "results": result["results"],
            "total_actions": result["total_actions"],
            "successful_actions": result["successful_actions"],
            "failed_actions": result["failed_actions"],
            "dry_run": result["dry_run"]
        },
        "executed_actions": list(executed_actions),  # Keep original executed_actions
        # In dry-run, we might want to keep actions for review
        "approved_actions": approved_actions
    }