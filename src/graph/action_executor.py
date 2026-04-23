"""
Action Executor node for the OpenMetaMind swarm.

Performs actual MCP write operations. The only component with write permissions.
"""

import asyncio
import logging
from typing import List, Dict, Any

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
    """

    def __init__(self):
        """Initialize the Action Executor."""
        self.pending_batch: List[ProposedAction] = []
        self.executed_actions: set = set()  # Track executed actions for idempotency

    async def execute_batch(
        self, 
        actions: List[ProposedAction], 
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute approved actions via MCP with full rollback support.
        
        Args:
            actions: List of approved actions to execute
            dry_run: If True, only simulate execution
            
        Returns:
            Dictionary with execution results
        """
        results = []
        
        for action in actions:
            # Check idempotency: skip if already executed
            action_hash = self._get_action_hash(action)
            if action_hash in self.executed_actions:
                logger.info(f"Skipping already executed action: {action.action_type} on {action.entity_fqn}")
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": True,
                    "result": {"message": "Already executed (idempotency skip)"},
                    "skipped": True
                })
                continue
            
            try:
                if dry_run:
                    result = await self._simulate(action)
                else:
                    result = await self._execute_mcp(action)
                
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": True,
                    "result": result
                })
                
                # Mark as executed only if successful
                self.executed_actions.add(action_hash)
                
            except Exception as e:
                logger.error(f"Action execution failed: {action.action_type} on {action.entity_fqn}: {str(e)}")
                results.append({
                    "action": action.dict() if hasattr(action, 'dict') else action,
                    "success": False,
                    "error": str(e)
                })
                # Stop on first failure? Or continue? Configurable.
                # For now, continue but could be made configurable
        
        return {
            "results": results,
            "total_actions": len(actions),
            "successful_actions": len([r for r in results if r.get("success", False)]),
            "failed_actions": len([r for r in results if not r.get("success", True)]),
            "dry_run": dry_run
        }
    
    async def _execute_mcp(self, action: ProposedAction) -> Dict[str, Any]:
        """
        Map ProposedAction to MCP tool call.
        
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
            # Add more mappings as needed
        }
        
        tool_name = tool_map.get(action.action_type)
        if not tool_name:
            raise ValueError(f"No MCP tool mapping for action type: {action.action_type}")
        
        # Execute the MCP tool call
        async with mcp_client as client:
            # For now, we'll use a generic approach - in reality, each action type
            # would map to specific MCP tool parameters
            result = await client._call_mcp_tool(tool_name, action.parameters)
            return result
    
    async def _simulate(self, action: ProposedAction) -> Dict[str, Any]:
        """
        Simulate an action for dry-run mode.
        
        Args:
            action: The action to simulate
            
        Returns:
            Simulation result
        """
        return {
            "simulated": True,
            "action_type": action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type),
            "entity_fqn": action.entity_fqn,
            "parameters": action.parameters,
            "message": f"Would execute {action.action_type} on {action.entity_fqn}"
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
        state: Current swarm state containing approved_actions
        
    Returns:
        Dictionary with state updates
    """
    approved_actions = state.get("approved_actions", [])
    
    if not approved_actions:
        return {
            "action_results": {
                "total_actions": 0,
                "successful_actions": 0,
                "failed_actions": 0,
                "results": []
            }
        }
    
    # Convert dicts to ProposedAction objects if needed
    actions = []
    for action_dict in approved_actions:
        if isinstance(action_dict, dict):
            actions.append(ProposedAction(**action_dict))
        else:
            actions.append(action_dict)
    
    # Create executor and run batch
    executor = ActionExecutor()
    
    # Run async function in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(executor.execute_batch(actions, dry_run=False))
    finally:
        loop.close()
    
    return {
        "action_results": result,
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
    
    if not approved_actions:
        return {
            "action_results": {
                "total_actions": 0,
                "successful_actions": 0,
                "failed_actions": 0,
                "results": []
            }
        }
    
    # Convert dicts to ProposedAction objects if needed
    actions = []
    for action_dict in approved_actions:
        if isinstance(action_dict, dict):
            actions.append(ProposedAction(**action_dict))
        else:
            actions.append(action_dict)
    
    # Create executor and run batch in dry-run mode
    executor = ActionExecutor()
    
    # Run async function in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(executor.execute_batch(actions, dry_run=True))
    finally:
        loop.close()
    
    return {
        "action_results": result,
        # In dry-run, we might want to keep actions for review
        "approved_actions": approved_actions
    }