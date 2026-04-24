# OpenMetaMind Refactoring Plan: Supervisor/Manager Pattern

## Overview

This document outlines the refactoring from the current **parallel agent execution** (using LangGraph Send API) to a **Supervisor/Manager pattern** for simpler, more reliable multi-agent orchestration.

## Why Refactor?

### Current Issues with Parallel (Send API):
1. **Concurrent state updates** cause `InvalidConcurrentGraphUpdate` errors
2. **Complex state management** with `Annotated[..., operator.add]` for accumulation
3. **Non-deterministic execution order** makes debugging difficult
4. **Complex routing logic** for managing parallel branches

### Benefits of Supervisor Pattern:
1. **Sequential execution** - no concurrent update conflicts
2. **Simple state updates** - just return plain dicts
3. **Easy to trace execution** - linear flow
4. **Supervisor synthesizes results** before moving to next step
5. **Much easier to debug and test**

---

## Architecture Comparison

### Current Architecture (Parallel Send API)

```
Coordinator → Planner → Dispatcher → [Send API spawns parallel agents]
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
              [Agent A]       [Agent B]       [Agent C]
                    │               │               │
                    └───────────────┼───────────────┘
                                    ↓
                            [Integrity Critic]
                                    ↓
                            [Action Executor]
```

### New Architecture (Supervisor/Manager)

```
Coordinator → Planner → Supervisor (loop)
                           ↓
                      [Agent A] → results
                           ↓
                      [Agent B] → results
                           ↓
                      [Agent C] → results
                           ↓
                      [Synthesize]
                           ↓
                    [Integrity Critic]
                           ↓
                    [Action Executor]
```

---

## Changes Required

### 1. State Schema (src/models/state.py)

**Current State:**
```python
class SwarmState(TypedDict):
    "findings": Annotated[List[AgentFinding], operator.add],  # Complex accumulation
    "agent_statuses": Annotated[Dict[str, str], operator.or_],
    "completed_subtasks": Annotated[List[str], operator.add],
    "blackboard": BlackboardState,  # Nested with operator.add annotations
```

**New State:**
```python
class SwarmState(TypedDict):
    "findings": List[AgentFinding],  # Simple list - Supervisor appends
    "agent_statuses": Dict[str, str],  # Simple dict - Supervisor updates
    "completed_subtasks": List[str],  # Simple list - Supervisor appends
    "blackboard": BlackboardState,  # Conflicts only
    "current_task_index": int,  # Track position in execution plan
    "pending_tasks": List[Subtask],  # Tasks yet to execute
```

### 2. Supervisor Node (src/graph/supervisor.py)

Create a new `Supervisor` node that replaces the Dispatcher. The Supervisor:
- Iterates through tasks in the execution plan sequentially
- Calls each agent and collects results
- Synthesizes findings after each agent completes
- Reports to the main graph flow

```python
class Supervisor:
    """Supervisor/Manager that orchestrates agents sequentially."""
    
    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute next pending task.
        Returns control to main graph after each agent.
        """
        pending_tasks = state.get("pending_tasks", [])
        if not pending_tasks:
            # All tasks done - move to critic
            return {"next": "integrity_critic"}
        
        # Get current task
        current_task = pending_tasks[0]
        
        # Execute agent
        result = self._execute_agent(current_task, state)
        
        # Update state with results
        updates = {
            "findings": state["findings"] + [result["finding"]],
            "agent_statuses": {current_task.agent_id: "completed"},
            "completed_subtasks": state["completed_subtasks"] + [current_task.subtask_id],
            "pending_tasks": pending_tasks[1:],  # Remove completed task
            "current_task_index": state.get("current_task_index", 0) + 1,
        }
        
        # Check if more tasks or done
        if pending_tasks[1:]:
            updates["next"] = "supervisor"  # Loop back
        else:
            updates["next"] = "integrity_critic"  # Move to critic
            
        return updates
```

### 3. Dispatcher Refactor (src/graph/dispatcher.py)

The dispatcher becomes a task queue manager:

```python
def dispatcher_node(state: SwarmState) -> Dict[str, Any]:
    """
    Initialize task queue from execution plan.
    Returns the first batch of tasks to execute.
    """
    plan = state.get("execution_plan")
    if not plan or not plan.subtasks:
        return {"next": "integrity_critic"}
    
    # Convert plan to pending tasks
    pending_tasks = [Subtask(**s) if isinstance(s, dict) else s for s in plan.subtasks]
    
    # Find tasks with no dependencies (first group)
    first_batch = [
        t for t in pending_tasks 
        if all(dep in state.get("completed_subtasks", []) for dep in t.dependencies)
    ]
    
    if not first_batch:
        return {"next": "integrity_critic"}
    
    return {
        "pending_tasks": pending_tasks,
        "current_task_index": 0,
        "next": "supervisor"
    }
```

### 4. Graph Routing (src/graph/swarm_graph.py)

**Current routing:**
```python
workflow.add_conditional_edges(
    "dispatcher",
    dispatcher_conditional_edge,  # Returns Send objects or node name
    {
        "agent_executor": "agent_executor",
        "integrity_critic": "integrity_critic"
    }
)
```

**New routing:**
```python
# Linear flow: dispatcher → supervisor → integrity_critic
workflow.add_edge("coordinator", "planner")
workflow.add_edge("planner", "dispatcher")
workflow.add_edge("dispatcher", "supervisor")
workflow.add_edge("supervisor", "integrity_critic")
workflow.add_edge("integrity_critic", "action_executor")
workflow.add_edge("action_executor", END)

# Conditional for supervisor loop
workflow.add_conditional_edges(
    "supervisor",
    lambda state: "supervisor" if state.get("pending_tasks") else "integrity_critic",
    {
        "supervisor": "supervisor",
        "integrity_critic": "integrity_critic"
    }
)
```

### 5. Agent Executor (src/graph/agent_executor.py)

**Current:** Uses Send API payload as state, runs async in loop

**New:** Simple synchronous function called by Supervisor

```python
def agent_executor_node(state: SwarmState) -> Dict[str, Any]:
    """
    Execute a single agent task.
    Called by Supervisor with task details in state.
    """
    task = state.get("current_task")
    if not task:
        return {"finding": None, "error": "No task provided"}
    
    # Create async executor
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(_execute_agent(task))
    loop.close()
    
    return {
        "finding": result,
        "agent_status": {task.agent_id: "completed"}
    }

async def _execute_agent(task: Subtask) -> AgentFinding:
    """Execute a single agent task."""
    agent = AgentRegistry().get_agent(task.agent_id)
    if not agent:
        return create_error_finding(task, "Agent not found")
    
    mcp_client = get_mcp_client()
    async with mcp_client as client:
        return await agent.execute(
            task=task.task_description,
            inputs=task.required_inputs,
            mcp_client=client
        )
```

### 6. Integrity Critic (src/graph/integrity_critic.py)

**Current:** Reads from `state["findings"]` (top-level with operator.add)

**New:** Reads from `state["findings"]` (simple list)

No changes needed - the interface stays the same.

### 7. Main API (src/main.py)

**Current:** Handles complex parallel state

**New:** Simple sequential flow

```python
async def run_swarm(query: SwarmQuery, graph):
    initial_state = {
        "user_query": query.query,
        "user_input": query.query,
        "conversation_history": [],
        "findings": [],
        "agent_statuses": {},
        "completed_subtasks": [],
        "pending_tasks": [],
    }
    
    final_state = await graph.ainvoke(initial_state, config=config)
    
    # Simple extraction
    return SwarmResponse(
        findings=final_state.get("findings", []),
        agent_statuses=final_state.get("agent_statuses", {}),
        coordinator_response=final_state.get("coordinator_response"),
    )
```

---

## File Changes Summary

| File | Change | Description |
|------|--------|-------------|
| `src/models/state.py` | Modify | Remove `Annotated[..., operator.add]` for findings, agent_statuses, completed_subtasks |
| `src/graph/dispatcher.py` | Refactor | Task queue initialization instead of Send spawning |
| `src/graph/supervisor.py` | Create | New Supervisor node for sequential execution |
| `src/graph/agent_executor.py` | Simplify | Remove Send API handling, simple task execution |
| `src/graph/swarm_graph.py` | Refactor | Linear routing instead of conditional Send |
| `src/graph/integrity_critic.py` | No change | Interface remains same |
| `src/main.py` | Simplify | Remove complex state handling |
| `tests/test_graph.py` | Update | Test new sequential flow |
| `tests/test_agents.py` | No change | Agent tests remain same |

---

## Migration Steps

### Step 1: Create Supervisor Node
- Create `src/graph/supervisor.py` with the Supervisor class

### Step 2: Update State Schema
- Remove `Annotated[..., operator.add]` from findings, agent_statuses, completed_subtasks
- Add `pending_tasks` and `current_task_index`

### Step 3: Refactor Dispatcher
- Change from Send API spawner to task queue initializer

### Step 4: Update Graph Routing
- Change to linear flow with supervisor loop

### Step 5: Simplify Agent Executor
- Remove Send API payload handling
- Simple task execution interface

### Step 6: Update Tests
- Modify test_graph.py for new flow

### Step 7: Verify
- Run all tests
- Test API endpoint

---

## Supervisor Node Pseudo-code

```python
# src/graph/supervisor.py

class Supervisor:
    """The Supervisor node - executes tasks sequentially and synthesizes results."""
    
    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Main supervisor logic:
        1. Check if there are pending tasks
        2. If yes, execute next task
        3. If no, move to integrity critic
        """
        pending_tasks = state.get("pending_tasks", [])
        
        if not pending_tasks:
            # All tasks completed - move to critic
            return {"next": "integrity_critic"}
        
        # Get and execute current task
        current_task = pending_tasks[0]
        logger.info(f"Supervisor executing task: {current_task.subtask_id}")
        
        # Execute agent
        finding = self._execute_agent_sync(current_task, state)
        
        # Update state
        new_findings = state.get("findings", []) + [finding]
        new_completed = state.get("completed_subtasks", []) + [current_task.subtask_id]
        remaining_tasks = pending_tasks[1:]
        
        if remaining_tasks:
            # More tasks to do - stay in supervisor loop
            return {
                "findings": new_findings,
                "completed_subtasks": new_completed,
                "pending_tasks": remaining_tasks,
                "agent_statuses": {current_task.agent_id: "completed"},
                "next": "supervisor"
            }
        else:
            # All done - move to critic
            return {
                "findings": new_findings,
                "completed_subtasks": new_completed,
                "pending_tasks": [],
                "agent_statuses": {current_task.agent_id: "completed"},
                "next": "integrity_critic"
            }
    
    def _execute_agent_sync(self, task, state) -> AgentFinding:
        """Synchronous wrapper for async agent execution."""
        inputs = self._prepare_inputs(task, state)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            finding = loop.run_until_complete(
                self._execute_agent_async(task, inputs)
            )
            return finding
        finally:
            loop.close()
    
    async def _execute_agent_async(self, task, inputs) -> AgentFinding:
        """Execute agent with MCP client."""
        agent = AgentRegistry().get_agent(task.agent_id)
        if not agent:
            return self._create_error_finding(task, f"Agent {task.agent_id} not found")
        
        mcp_client = get_mcp_client()
        async with mcp_client as client:
            return await agent.execute(
                task=task.task_description,
                inputs=inputs,
                mcp_client=client
            )
    
    def _prepare_inputs(self, task, state) -> Dict[str, Any]:
        """Prepare inputs for agent from blackboard."""
        blackboard = state.get("blackboard", {})
        inputs = {}
        for key in task.required_inputs:
            if key in blackboard:
                inputs[key] = blackboard[key]
        return inputs
    
    def _create_error_finding(self, task, error_msg) -> AgentFinding:
        """Create error finding when agent fails."""
        return AgentFinding(
            agent_id=task.agent_id,
            subtask_id=task.subtask_id,
            task_description=task.task_description,
            finding_type=FindingType.OTHER,
            summary=f"Task failed: {error_msg}",
            confidence=0.0
        )
```

---

## Testing Strategy

1. **Unit tests for Supervisor** - Test task iteration, state updates
2. **Integration tests for graph flow** - Test full coordinator → supervisor → critic flow
3. **API tests** - Verify endpoint returns correct findings

---

## Rollback Plan

If issues arise, the parallel implementation is preserved in git. Can revert to Send API pattern if needed.

---

## Timeline

1. Create Supervisor node: 30 min
2. Update state schema: 15 min
3. Refactor dispatcher: 20 min
4. Update graph routing: 15 min
5. Update agent executor: 15 min
6. Update tests: 30 min
7. Verification: 20 min

**Total estimated time: ~2 hours**