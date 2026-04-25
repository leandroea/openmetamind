"""
Action Executor node for the OpenMetaMind swarm.

Performs actual MCP write operations. The only component with write permissions.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Set, Optional

from ..models.state import SwarmState, ProposedAction, ActionType
from ..mcp.client import get_mcp_client, OpenMetadataMCPClient
from ..mcp.models import Entity, TableProfile, ColumnProfile, UsageStats

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
                logger.info(f"Skipping already executed action: {action.action_type} on {action.target_entity}")
                results.append({
                    "action": action.model_dump() if hasattr(action, 'model_dump') else action,
                    "success": True,
                    "result": {"message": "Already executed (idempotency skip)"},
                    "skipped": True
                })
                continue
            
            # Check if we've already executed this action in this batch (double-check)
            if action_hash in newly_executed:
                logger.info(f"Skipping duplicate action in batch: {action.action_type} on {action.target_entity}")
                results.append({
                    "action": action.model_dump() if hasattr(action, 'model_dump') else action,
                    "success": True,
                    "result": {"message": "Already executed in this batch (idempotency skip)"},
                    "skipped": True
                })
                continue
            
            try:
                if dry_run:
                    # In dry-run mode, we still want to validate the action would work
                    # For now, we'll simulate but log what we would do
                    logger.info(f"DRY RUN: Would execute {action.action_type} on {action.target_entity}")
                    result = await self._validate_action(action)
                else:
                    # Actually execute the MCP call
                    result = await self._execute_mcp(action)
                
                results.append({
                    "action": action.model_dump() if hasattr(action, 'model_dump') else action,
                    "success": True,
                    "result": result
                })
                
                # Mark as executed only if successful
                newly_executed.add(action_hash)
                
                # If fail_fast is True and we had a failure, we would have raised an exception
                # Since we're continuing, we just keep track of successes
                
            except Exception as e:
                logger.error(f"Action execution failed: {action.action_type} on {action.target_entity}: {str(e)}")
                results.append({
                    "action": action.model_dump() if hasattr(action, 'model_dump') else action,
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
        
        # Map action type to MCP method
        action_methods = {
            ActionType.ASSIGN_TAG: lambda client, action: client.add_tags(
                fqn=action.target_entity,
                entity_type=action.parameters.get("entity_type", "table"),
                tags=action.parameters.get("tags", [])
            ),
            ActionType.UPDATE_OWNER: lambda client, action: client.add_owner(
                fqn=action.target_entity,
                entity_type=action.parameters.get("entity_type", "table"),
                owner=action.parameters.get("owner"),
                owner_type=action.parameters.get("owner_type", "user")
            ),
            ActionType.CREATE_GLOSSARY_TERM: lambda client, action: client.create_glossary_term(
                glossary=action.parameters.get("glossary"),
                name=action.parameters.get("name"),
                description=action.parameters.get("description", ""),
                parent_term=action.parameters.get("parent_term"),
                owners=action.parameters.get("owners")
            ),
            ActionType.UPDATE_LINEAGE: lambda client, action: client._call_mcp_tool(
                "update_lineage", action.parameters
            ),
            ActionType.ADD_OWNER: lambda client, action: client.add_owner(
                fqn=action.target_entity,
                entity_type=action.parameters.get("entity_type", "table"),
                owner=action.parameters.get("owner"),
                owner_type=action.parameters.get("owner_type", "user")
            ),
            ActionType.REMOVE_OWNER: lambda client, action: client.remove_owner(
                fqn=action.target_entity,
                entity_type=action.parameters.get("entity_type", "table"),
                owner=action.parameters.get("owner")
            ),
            ActionType.DELETE_TAG: lambda client, action: client.delete_tag(
                fqn=action.target_entity,
                entity_type=action.parameters.get("entity_type", "table"),
                tag=action.parameters.get("tag")
            ),
        }

        # Special handling for ADD_DESCRIPTION - use patch_entity with logging
        if action.action_type == ActionType.ADD_DESCRIPTION:
            async with mcp_client as client:
                entity_type = action.parameters.get("entity_type", "table")
                entity_fqn = action.target_entity
                description = action.parameters.get("description", "")
                patch_payload = OpenMetadataMCPClient.build_description_patch(description)
                
                logger.info(f"Executing ADD_DESCRIPTION via patch_entity for {entity_fqn}")
                logger.debug(f"Patch payload: {json.dumps(patch_payload)}")
                logger.debug(f"Entity type: {entity_type}, path: /description")
                
                result = await client.patch_entity(
                    entity_type=entity_type,
                    fqn=entity_fqn,
                    patch=patch_payload
                )
                return result

        action_method = action_methods.get(action.action_type)
        if not action_method:
            raise ValueError(f"No MCP tool mapping for action type: {action.action_type}")

        # Execute the MCP tool call using the helper method
        async with mcp_client as client:
            result = await action_method(client, action)
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
            "entity_fqn": action.target_entity,
            "parameters": action.parameters,
            "message": f"DRY RUN: Validated {action.action_type} on {action.target_entity} - would execute in live mode"
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
        action_str = f"{action.action_type}:{action.target_entity}:{str(sorted(action.parameters.items()))}"
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


# =============================================================================
# Standalone Human Approval Execution Functions
# These functions allow the Streamlit UI to manually trigger action execution
# after the Critic escalates to human review.
# =============================================================================

async def _execute_single_action(
    action_dict: Dict[str, Any],
    mcp_client: OpenMetadataMCPClient
) -> Dict[str, Any]:
    """
    Execute a single action via MCP.
    
    Args:
        action_dict: Dictionary representing the action
        mcp_client: Active MCP client context manager
        
    Returns:
        Result dictionary with success status and details
    """
    action_type = action_dict.get("action_type", "")
    entity_fqn = action_dict.get("target_entity", "")
    parameters = action_dict.get("parameters", {})
    entity_type = parameters.get("entity_type", "table")
    
    # ADD_DESCRIPTION uses patch_entity with JSON Patch
    if action_type in ("ADD_DESCRIPTION", "add_description"):
        description = parameters.get("description", "")
        logger.info(f"Executing ADD_DESCRIPTION via patch_entity for {entity_fqn}")
        logger.debug(f"Patch payload: {json.dumps([{'op': 'add', 'path': '/description', 'value': description}])}")
        result = await mcp_client.patch_entity(
            entity_type=entity_type,
            fqn=entity_fqn,
            patch=[{"op": "add", "path": "/description", "value": description}]
        )
        return {
            "success": True,
            "action_type": action_type,
            "entity_fqn": entity_fqn,
            "result": result
        }
    else:
        logger.warning(f"Action type '{action_type}' not yet supported for manual execution")
        return {
            "success": False,
            "action_type": action_type,
            "entity_fqn": entity_fqn,
            "error": f"Action type '{action_type}' not yet supported for manual execution"
        }


async def execute_pending_actions_async(
    actions: List[Dict[str, Any]],
    mcp_client: OpenMetadataMCPClient = None
) -> Dict[str, Any]:
    """
    Execute a list of pending actions via MCP.
    
    This is a standalone async function that can be called from outside the
    LangGraph workflow, such as when a human clicks "Approve All" in the UI.
    
    Args:
        actions: List of action dictionaries (from pending_human_actions)
        mcp_client: Optional MCP client. If not provided, will obtain one.
        
    Returns:
        Summary dictionary with:
        - total_actions: How many actions were attempted
        - successful_actions: How many succeeded
        - failed_actions: How many failed
        - results: List of per-action results
    """
    results = []
    successful = 0
    failed = 0
    
    # Get MCP client if not provided
    if mcp_client is None:
        client = get_mcp_client()
    else:
        client = mcp_client
    
    try:
        async with client as mc:
            for action_dict in actions:
                try:
                    result = await _execute_single_action(action_dict, mc)
                    results.append(result)
                    if result.get("success", False):
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Failed to execute action {action_dict.get('action_type')} on {action_dict.get('entity_fqn')}: {str(e)}")
                    results.append({
                        "success": False,
                        "action_type": action_dict.get("action_type", "UNKNOWN"),
                        "target_entity": action_dict.get("target_entity", "UNKNOWN"),
                        "error": str(e)
                    })
                    failed += 1
    except Exception as e:
        logger.error(f"MCP client error: {str(e)}")
        # Let the error propagate after async with has cleaned up
        raise
    # Note: async with handles cleanup via __aexit__, no explicit close() needed
    
    return {
        "total_actions": len(actions),
        "successful_actions": successful,
        "failed_actions": failed,
        "results": results
    }


def execute_pending_actions(
    actions: List[Dict[str, Any]],
    mcp_client: OpenMetadataMCPClient = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for execute_pending_actions_async.
    
    This allows Streamlit button callbacks to call the execution function
    directly without dealing with async/await.
    
    Args:
        actions: List of action dictionaries (from pending_human_actions)
        mcp_client: Optional MCP client. If not provided, will obtain one.
        
    Returns:
        Summary dictionary with execution results
    """
    return asyncio.run(execute_pending_actions_async(actions, mcp_client))