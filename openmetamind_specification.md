# OpenMetaMind: Technical Specification
## Autonomous Multi-Agent Swarm for OpenMetadata Data Governance

---

## 1. Core Philosophy

**Thesis:** Data governance is not a single task performed by a single AI. It is a distributed cognitive process requiring multiple specialists who investigate, debate, validate, and execute — just like a human data governance team. The platform must make this collective intelligence **visible, auditable, and extensible**.

**Anti-Thesis (what we reject):**
- Single-chatbot approaches (ChatGPT with a governance prompt)
- Static workflow automation with AI sprinkled on top
- Black-box AI that makes changes without showing its work
- Hardcoded agent teams that require code changes to evolve

---

## 2. Architectural Principles

| Principle | Manifestation |
|-----------|---------------|
| **Swarm over Singleton** | Multiple independent agents with distinct roles, not one agent with multiple prompts |
| **Visible Cognition** | Every agent's reasoning, findings, and conflicts are displayed in real-time |
| **Dynamic Composition** | Agents self-assemble per task; no pre-built workflow templates |
| **Extensibility by Addition** | New agents are drop-in plugins, not graph rewrites |
| **Human Sovereignty** | AI proposes, human approves; the swarm serves, it does not replace |
| **Native Protocol** | All operations flow through OpenMetadata's MCP server, not wrapper APIs |

---

## 3. System Architecture

### 3.1 High-Level Flow

```
+-------------+     +-------------+     +-----------------------------+
|   USER      |---->| COORDINATOR |---->|        PLANNER              |
|  (Chat/Slack|     |  (LangGraph |     |  - Decomposes task          |
|   /Teams)   |     |   Node)     |     |  - Queries Agent Registry   |
+-------------+     +-------------+     |  - Generates execution DAG  |
          ^                             +-----------------------------+
          |                                          |
          |                                          v
          |                             +-----------------------------+
          |                             |      DISPATCHER             |
          |                             |  - Initializes task queue   |
          |                             |  - Sets execution order     |
          |                             +-----------------------------+
          |                                          |
          |                                          v
          |                             +-----------------------------+
          |                             |      SUPERVISOR              |
          |                             |  - Iterates through tasks   |
          |                             |  - Calls agents sequentially|
          |                             |  - Synthesizes results      |
          |                             +-----------------------------+
          |                                          |
          |                           +--------------+---------------+
          |                           v                              v
          |                   +-------------+              +-------------+
          |                   |  Agent A    |              |  Agent B    |
          |                   |  (Plugin)   |              |  (Plugin)   |
          |                   +------+------+              +------+------+
          |                          |                              |
          |                          +--------------+---------------+
          |                                         v
          |                          +-----------------------------+
          |                          |      BLACKBOARD             |
          |                          |  (Append-only shared state) |
          |                          +-----------------------------+
          |                                         |
          |                                         v
          |                          +-----------------------------+
          |                          |   INTEGRITY CRITIC          |
          |                          |  - Validates all findings   |
          |                          |  - Detects conflicts        |
          |                          |  - Assigns confidence       |
          |                          +-----------------------------+
          |                                         |
          |                          +------------+------------+
          |                          v                         v
          |               +-----------------+      +-----------------+
          |               | AUTO-APPROVE    |      | HUMAN GATE      |
          |               | (confidence >   |      | (Streamlit/     |
          |               |  threshold)     |      |  Slack/Teams)   |
          |               +--------+--------+      +--------+--------+
          |                        |                        |
          |                        +------------+-----------+
          |                                     v
          |                          +-----------------------------+
          |                          |    ACTION EXECUTOR          |
          |                          |  - MCP write operations     |
          |                          |  - Batched, idempotent      |
          |                          +-----------------------------+
          |                                     |
          +-------------------------------------+
                        (Response + Audit Trail)
```

### 3.2 Component Deep-Dives

#### 3.2.1 The Coordinator (coordinator.py)

**Role:** The user's single point of contact. Maintains conversation memory. Decides whether to answer directly, delegate to swarm, or ask clarifying questions.

**State:**
```python
class CoordinatorState(BaseModel):
    conversation_history: List[Message]  # Full chat context
    user_intent: Optional[IntentClassification]
    delegated_task: Optional[str]
    swarm_summary: Optional[SwarmResult]
    requires_clarification: bool
```

**Decision Logic:**
```
IF user_query is follow-up about previous swarm run:
    -> Answer directly from swarm_summary + blackboard history
ELIF user_query is simple factual (e.g., 'what is the schema of X?'):
    -> Delegate lightweight (single agent, no critic)
ELIF user_query is complex governance task:
    -> Delegate full swarm (planner + multi-agent + critic)
ELIF user_query is ambiguous:
    -> Ask clarifying question
```

**Output Format to User:**
```
"I am dispatching the Catalog Scout and Quality Guardian to investigate.
The Scout will map the structure; the Guardian will analyze data quality.
I will synthesize their findings once they are done.

[Swarm Theater appears in UI]

---

"Results from the swarm:

- Catalog Scout found 12 tables [view details]
- Quality Guardian flagged 2 tables with stale profiles [view details]
- Integrity Critic validated all findings at >0.9 confidence

Proposed actions:
[1] Tag 3 PII columns - Approve / Reject / Modify
[2] Assign owner to 'orders' table - Approve / Reject
"
```

#### 3.2.2 The Planner (planner.py)

**Role:** Task decomposition and agent selection. The "project manager" of the swarm.

**Input:** Natural language task + Agent Registry capabilities

**Output:** Execution DAG (list of Subtask objects with dependencies)

```python
class Subtask(BaseModel):
    subtask_id: str
    agent_id: str
    task_description: str
    required_inputs: List[str]  # Keys from blackboard needed
    produces_output: str        # Key written to blackboard
    dependencies: List[str]     # subtask_ids that must complete first
    max_retries: int = 2
    timeout_seconds: int = 60

class ExecutionPlan(BaseModel):
    subtasks: List[Subtask]
    estimated_duration: str
```

**Important:** The Planner generates a task list but agents execute **sequentially** via the Supervisor pattern, not in parallel. The `parallel_groups` field is deprecated - use `dependencies` to define ordering.

**Example Decomposition:**

User: "Audit the customers database and fix governance gaps"

The Planner decomposes this into a task list with dependencies:

```yaml
plan:
  subtasks:
    - id: discover_tables
      agent: catalog_scout
      task: "List all tables in customers database"
      produces: table_list
      dependencies: []
      
    - id: check_classifications
      agent: data_steward  
      task: "Check existing tags and classifications"
      produces: current_classifications
      dependencies: []
      
    - id: profile_quality
      agent: quality_guardian
      task: "Profile all tables from table_list"
      produces: quality_reports
      dependencies: [discover_tables]
      
    - id: check_compliance
      agent: policy_enforcer
      task: "Check compliance status of current_classifications"
      produces: compliance_gaps
      dependencies: [check_classifications]
      
    - id: generate_docs
      agent: documentation_expert
      task: "Generate missing descriptions for tables lacking them"
      produces: proposed_descriptions
      dependencies: [discover_tables, profile_quality]
      
    - id: validate_findings
      agent: integrity_critic
      task: "Validate all findings and proposed actions"
      produces: critic_review
      dependencies: [profile_quality, check_compliance, generate_docs]
```

**Execution Order:** The Supervisor iterates through tasks in dependency order (as defined by topological sort), executing one agent at a time and synthesizing results before moving to the next task.

#### 3.2.3 The Dispatcher (dispatcher.py)

**Role:** Initializes the task queue from the Planner's execution plan. Sets up the execution order for the Supervisor.

**Implementation:**
```python
def dispatcher_node(state: SwarmState):
    plan = state['execution_plan']
    
    # Convert plan subtasks to pending task queue
    pending_tasks = []
    for subtask in plan.subtasks:
        pending_tasks.append({
            "subtask_id": subtask.subtask_id,
            "agent_id": subtask.agent_id,
            "task": subtask.task_description,
            "inputs": subtask.required_inputs,
            "dependencies": subtask.dependencies,
            "produces_output": subtask.produces_output
        })
    
    return {
        "pending_tasks": pending_tasks,
        "current_task_index": 0,
        "next": "supervisor"
    }
```

**Key Feature:** Dynamic replanning. If an agent fails or returns unexpected results, the Planner can regenerate the DAG mid-execution.

#### 3.2.4 The Supervisor (supervisor.py)

**Role:** The Supervisor/Manager that orchestrates agent execution sequentially. After each agent completes, the Supervisor synthesizes results and decides whether to continue the loop or move to the Integrity Critic.

**Implementation:**
```python
class Supervisor:
    """The Supervisor node - executes tasks sequentially and synthesizes results."""
    
    def __call__(self, state: SwarmState):
        pending_tasks = state.get("pending_tasks", [])
        
        if not pending_tasks:
            # All tasks completed - move to critic
            return {"next": "integrity_critic"}
        
        # Get and execute current task
        current_task = pending_tasks[0]
        
        # Execute the agent for this task
        finding = self._execute_agent(current_task, state)
        
        # Update state with results
        new_findings = state.get("findings", []) + [finding]
        new_completed = state.get("completed_subtasks", []) + [current_task["subtask_id"]]
        remaining_tasks = pending_tasks[1:]
        
        if remaining_tasks:
            # More tasks to do - stay in supervisor loop
            return {
                "findings": new_findings,
                "completed_subtasks": new_completed,
                "pending_tasks": remaining_tasks,
                "agent_statuses": {current_task["agent_id"]: "completed"},
                "next": "supervisor"
            }
        else:
            # All done - move to critic
            return {
                "findings": new_findings,
                "completed_subtasks": new_completed,
                "pending_tasks": [],
                "agent_statuses": {current_task["agent_id"]: "completed"},
                "next": "integrity_critic"
            }
```

**Supervisor Loop Flow:**
```
Supervisor called with pending_tasks = [TaskA, TaskB, TaskC]

1. Execute TaskA → Agent returns FindingA
2. Update state: findings = [FindingA], pending_tasks = [TaskB, TaskC]
3. Return "next": "supervisor" → Loop back

4. Execute TaskB → Agent returns FindingB
5. Update state: findings = [FindingA, FindingB], pending_tasks = [TaskC]
6. Return "next": "supervisor" → Loop back

7. Execute TaskC → Agent returns FindingC
8. Update state: findings = [FindingA, FindingB, FindingC], pending_tasks = []
9. Return "next": "integrity_critic" → Move to critic
```

**Benefits of Supervisor Pattern:**
- Sequential execution eliminates concurrent state update conflicts
- Linear flow makes debugging and tracing straightforward
- Each agent result is immediately synthesized before moving to next
- No complex parallel group management needed

#### 3.2.4 Agent Registry (agents/registry.py)

**Core abstraction:** Plugin system where agents self-register on import.

```python
class SwarmAgent(ABC):
    """Every agent in the swarm implements this interface."""
    
    @property
    @abstractmethod
    def agent_id(self) -> str: ...
    
    @property
    @abstractmethod
    def display_name(self) -> str: ...
    
    @property
    @abstractmethod
    def description(self) -> str: ...
    
    @property
    @abstractmethod
    def avatar_emoji(self) -> str: ...
    
    @property
    @abstractmethod
    def capabilities(self) -> List[Capability]: ...
    
    @property
    def default_confidence_threshold(self) -> float:
        return 0.8
    
    @abstractmethod
    async def can_handle(self, task_description: str) -> float:
        """Return 0.0-1.0 confidence that this agent can handle the task."""
        ...
    
    @abstractmethod
    async def execute(self, task: str, inputs: Dict, mcp_client: MCPClient) -> AgentFinding:
        """Execute the agent's core logic."""
        ...
    
    @property
    def requires_human_approval(self) -> bool:
        """If True, all actions from this agent go through human gate."""
        return False
```

**Registration Pattern:**
```python
# In each agent file (e.g., agents/data_steward.py)

class DataSteward(SwarmAgent):
    agent_id = "data_steward"
    display_name = "Data Steward"
    description = "Handles data classification, PII detection, tag assignment, and ownership management"
    avatar_emoji = "shield"
    
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
    
    async def can_handle(self, task_description: str) -> float:
        # Use lightweight embedding similarity or keyword matching
        # Return >0.6 to be considered by planner
        pass
    
    async def execute(self, task, inputs, mcp_client):
        # 1. Call MCP tools to gather data
        # 2. Use LLM to analyze
        # 3. Return structured finding
        pass
```

**Discovery by Planner:**
```python
class AgentRegistry:
    def find_agents_for_task(self, task: str, min_confidence: float = 0.6) -> List[AgentMatch]:
        """Query all registered agents for task suitability."""
        matches = []
        for agent in self._agents.values():
            score = await agent.can_handle(task)
            if score >= min_confidence:
                matches.append(AgentMatch(agent=agent, confidence=score))
        return sorted(matches, key=lambda x: x.confidence, reverse=True)
```

#### 3.2.5 The Blackboard (state.py)

**Design:** Append-only event log, not a mutable shared dictionary. Every agent writes findings; no agent overwrites another.

```python
class AgentFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_id: str
    subtask_id: str
    task_description: str
    
    # The actual output
    finding_type: FindingType  # classification, quality, compliance, etc.
    target_entity: Optional[str]  # FQN of table/column/etc
    summary: str  # Human-readable summary
    details: Dict[str, Any]  # Structured data
    confidence: float  # 0.0-1.0
    
    # Proposed actions (if any)
    proposed_actions: List[ProposedAction] = []
    
    # Raw evidence
    mcp_tool_calls: List[MCPToolCall] = []
    llm_reasoning: Optional[str]  # Chain-of-thought (for audit)

class BlackboardState(TypedDict):
    findings: Annotated[List[AgentFinding], operator.add]  # Append-only
    conflicts: Annotated[List[Conflict], operator.add]
    agent_statuses: Dict[str, AgentStatus]
    execution_phase: str  # planning, executing, reviewing, awaiting_approval, completed
    
class Conflict(BaseModel):
    conflict_id: str
    finding_ids: List[str]  # Which findings conflict
    agents_involved: List[str]
    description: str  # "Agent A says X, Agent B says not-X"
    severity: str  # warning, critical
    resolution: Optional[str]  # How Integrity Critic resolved it
```

#### 3.2.6 Integrity Critic (integrity_critic.py)

**Role:** Not just a "validator." A true critic that reads the blackboard, detects contradictions, assigns final confidence, and decides routing.

```python
class CriticReview(BaseModel):
    review_id: str
    findings_reviewed: int
    conflicts_detected: int
    conflicts_resolved: int
    conflicts_escalated: int
    
    # Per-finding assessment
    finding_assessments: List[FindingAssessment]
    
    # Final routing decision
    decision: CriticDecision  # AUTO_APPROVE, ESCALATE_TO_HUMAN, REJECT_AND_RETRY
    reasoning: str
    
    # Aggregated proposed actions
    approved_actions: List[ProposedAction]
    rejected_actions: List[ProposedAction]
    escalated_actions: List[ProposedAction]

class FindingAssessment(BaseModel):
    finding_id: str
    validity_score: float  # 0.0-1.0
    is_consistent_with_others: bool
    has_sufficient_evidence: bool
    mcp_calls_verified: bool  # Did the tools actually return what agent claims?
```

**Conflict Detection Examples:**

| Scenario | Agent A Says | Agent B Says | Critic Action |
|----------|-------------|--------------|---------------|
| Classification conflict | email is PII.Sensitive | email is PII.Internal | Check policy rules; if ambiguous -> escalate |
| Quality contradiction | Table has 0% nulls | Table has 15% nulls | Verify MCP profiler timestamps; flag stale data |
| Ownership dispute | Propose owner: @sales | Propose owner: @marketing | Check lineage upstream owners; escalate |
| False positive risk | Tag 50 columns as PII | - | Sample 5 columns manually; if pattern holds, approve |

#### 3.2.7 Action Executor (action_executor.py)

**Role:** Performs actual MCP write operations. The only component with write permissions.

```python
class ActionExecutor:
    def __init__(self):
        self.pending_batch: List[ProposedAction] = []
    
    async def execute_batch(self, actions: List[ProposedAction], dry_run: bool = False) -> BatchResult:
        """Execute approved actions via MCP with full rollback support."""
        
        results = []
        for action in actions:
            try:
                if dry_run:
                    result = await self._simulate(action)
                else:
                    result = await self._execute_mcp(action)
                results.append(ActionResult(action=action, success=True, result=result))
            except Exception as e:
                results.append(ActionResult(action=action, success=False, error=str(e)))
                # Stop on first failure? Or continue? Configurable.
                if self.fail_fast:
                    await self._rollback(results)
                    break
        
        return BatchResult(results=results)
    
    async def _execute_mcp(self, action: ProposedAction):
        """Map ProposedAction to MCP tool call."""
        tool_map = {
            ActionType.ASSIGN_TAG: "add_tags",
            ActionType.UPDATE_OWNER: "update_owner",
            ActionType.ADD_DESCRIPTION: "update_description",
            ActionType.CREATE_GLOSSARY_TERM: "create_glossary_term",
            # ... etc
        }
        tool_name = tool_map[action.action_type]
        return await mcp_client.call_tool(tool_name, action.parameters)
```

**Idempotency:** Every action hash (entity_fqn + action_type + parameters) is checked against `executed_actions` table before execution. Prevents duplicate writes if workflow retries.

---

## 4. User Interface Architecture

### 4.1 Streamlit Admin Dashboard

**Layout: Three-Panel Command Center**

```
+-----------------------------------------------------------------------------+
|  brain OpenMetaMind Coordinator    |  Active Swarms: 3  |  MCP Status: green     |
+-----------------------------------------------------------------------------+
|                                                                             |
|  +----------------------+  +---------------------------------------------+ |
|  |  PANEL 1: CHAT       |  |  PANEL 2: SWARM THEATER                     | |
|  |                      |  |                                             | |
|  |  User: 'Audit the    |  |   +-------------------------------------+   | |
|  |  customers db'       |  |   |  MISSION: Audit customers           |   | |
|  |                      |  |   |  Status: yellow Executing               |   | |
|  |  Coordinator: 'I'm   |  |   |  Duration: 12.4s                    |   | |
|  |  deploying 4 agents  |  |   +-------------------------------------+   | |
|  |  to investigate...'  |  |                                             | |
|  |                      |  |   green Catalog Scout        DONE    3.2s      | |
|  |  [Swarm Theater      |  |   green Data Steward         DONE    4.1s      | |
|  |   appears ->]        |  |   yellow Quality Guardian     RUNNING 8.4s      | |
|  |                      |  |      [##############        ] 67%             | |
|  |  Coordinator: 'The   |  |   yellow Policy Enforcer      RUNNING 8.4s      | |
|  |  swarm found...'     |  |      [##############        ] 67%             | |
|  |                      |  |   white Integrity Critic     WAITING           | |
|  |  [Approve] [Reject]  |  |   white Action Executor      IDLE              | |
|  |                      |  |                                             | |
|  +----------------------+  |   clipboard BLACKBOARD (7 findings)                | |
|                            |   - Scout: 12 tables discovered             | |
|                            |   - Steward: 3 PII columns detected [94%]   | |
|                            |   - Steward: 2 tables lack owners           | |
|                            |   - Guardian: 1 SLA violation (orders)      | |
|                            |   - ...                                     | |
|                            |                                             | |
|                            |   warning CONFLICTS (1)                          | |
|                            |   - Steward vs Enforcer on `ssn` tagging    | |
|                            |     [View Details] [Override]               | |
|                            |                                             | |
|                            +---------------------------------------------+ |
|                                                                             |
|  +---------------------------------------------------------------------+   |
|  |  PANEL 3: EXECUTION DAG (Live Graphviz)                             |   |
|  |                                                                     |   |
|  |    Coordinator ---> Planner ---> [Scout] ---\                       |   |
|  |                                [Steward]--\-\---> Blackboard ---> Critic   | |
|  |                                [Guard] ---/      ^                |   |
|  |                                [Enforcer]--------/                |   |
|  |                                                                     |   |
|  +---------------------------------------------------------------------+   |
|                                                                             |
+-----------------------------------------------------------------------------+
```

### 4.2 Slack/Teams Integration

**Thread-Based Swarm Interaction:**

**User in Slack:**
```
@openmetamind audit the customers database
```

**Coordinator creates thread:**
```
brain Coordinator: On it. Deploying swarm...

yellow Planner: Breaking down task...
   - 4 subtasks identified
   - Estimated time: 15s

green Catalog Scout: Found 12 tables
   - raw_customers.users, .orders, .events, ...

green Data Steward: Analysis complete
   - 3 PII columns detected
   - 2 tables missing owners
   [View Full Report]

yellow Quality Guardian: Profiling...
   - [########          ] 40%

yellow Policy Enforcer: Checking compliance...
   - [########          ] 40%
```

**After completion:**
```
white_check_mark Swarm complete. 7 findings, 1 conflict, 3 proposed actions.

clipboard Proposed Actions:
[1] Tag `users.email` as PII.Sensitive (confidence: 94%)
    [Approve] [Reject] [Modify]

[2] Assign owner `sales-ops` to `orders` table (confidence: 87%)
    [Approve] [Reject] [Modify]

[3] Update description for `events` table (confidence: 91%)
    [Approve] [Reject] [Modify]

[Approve All] [Review Individually] [Ask Question]
```

**Follow-up in same thread:**
```
User: Why did the Steward tag email as PII?

Coordinator: The Data Steward detected `email` as PII.Sensitive because:
- Pattern match: Contains '@' and domain (regex confidence: 98%)
- Column name semantic match: "email" (embedding confidence: 99%)
- Existing similar columns in org are tagged PII.Sensitive
- Policy rule: 'Any column containing contact info -> PII.Sensitive'

The Integrity Critic verified this finding against:
- MCP tool `get_column_profile` (actual data sampled)
- Policy document v2.3 (section 4.1)
- No conflicts with other agents

[View MCP Call Log] [View Policy Reference]
```

---

## 5. Agent Plugin Ecosystem

### 5.1 Core Agents (Shipped)

| Agent | ID | Role | Key Capabilities |
|-------|-----|------|------------------|
| Catalog Scout | `catalog_scout` | Discovery | `list_entities`, `search_catalog`, `get_entity_details` |
| Data Steward | `data_steward` | Classification | `detect_pii`, `assign_tags`, `manage_ownership` |
| Quality Guardian | `quality_guardian` | Data Quality | `profile_table`, `detect_anomalies`, `validate_sla` |
| Policy Enforcer | `policy_enforcer` | Compliance | `check_policy`, `validate_access`, `flag_violations` |
| Impact Analyst | `impact_analyst` | Lineage | `trace_lineage`, `map_dependencies`, `assess_change_impact` |
| Documentation Expert | `doc_expert` | Metadata | `generate_descriptions`, `create_readme`, `suggest_glossary_terms` |
| Integrity Critic | `integrity_critic` | Validation | `validate_findings`, `detect_conflicts`, `assign_confidence` |
| Action Executor | `action_executor` | Execution | `execute_mcp_write`, `batch_operations`, `rollback` |

### 5.2 Example: Adding a New Agent

**Scenario:** You want a `CostOptimizer` agent that identifies unused tables driving storage costs.

**Step 1:** Create `agents/cost_optimizer.py`

```python
from .base import SwarmAgent, Capability

class CostOptimizer(SwarmAgent):
    agent_id = "cost_optimizer"
    display_name = "Cost Optimizer"
    description = "Identifies unused tables and suggests archival to reduce storage costs"
    avatar_emoji = "money"
    
    capabilities = [
        Capability(
            name="storage_analysis",
            description="Analyzes table size, access patterns, and storage costs",
            input_schema={"database": "string", "lookback_days": "int"},
            output_schema={"unused_tables": "list[TableCostReport]"}
        ),
        Capability(
            name="archival_recommendation",
            description="Suggests archival strategy for unused tables",
            input_schema={"table_fqn": "string"},
            output_schema={"recommendation": "ArchivalRecommendation"}
        )
    ]
    
    async def can_handle(self, task: str) -> float:
        keywords = ["cost", "storage", "unused", "archive", "optimize", "expensive"]
        return semantic_similarity(task, keywords)
    
    async def execute(self, task, inputs, mcp_client):
        # Query MCP for usage stats, table sizes
        tables = await mcp_client.call_tool("list_entities", {
            "type": "table",
            "database": inputs.get("database")
        })
        
        # Analyze each table
        reports = []
        for table in tables:
            profile = await mcp_client.call_tool("get_table_profile", {"fqn": table.fqn})
            usage = await mcp_client.call_tool("get_usage_stats", {
                "fqn": table.fqn,
                "days": inputs.get("lookback_days", 90)
            })
            
            if usage.query_count == 0 and profile.size_bytes > 1_000_000_000:
                reports.append({
                    "table": table.fqn,
                    "size_gb": profile.size_bytes / 1e9,
                    "last_queried": usage.last_query_date,
                    "estimated_monthly_cost": profile.size_bytes * 0.023 / 1e9  # S3 pricing
                })
        
        return AgentFinding(
            agent_id=self.agent_id,
            finding_type="cost_optimization",
            summary=f"Found {len(reports)} unused tables costing ${sum(r['estimated_monthly_cost'] for r in reports):.2f}/month",
            details={"reports": reports},
            confidence=0.92,
            proposed_actions=[
                ProposedAction(
                    action_type="tag_for_archival",
                    target_entity=r["table"],
                    parameters={"tag": "cost.archive_candidate"}
                ) for r in reports[:5]  # Top 5
            ]
        )

# Auto-register
AgentRegistry.get_instance().register(CostOptimizer())
```

**Step 2:** Import in `agents/__init__.py`

```python
from .cost_optimizer import CostOptimizer  # That's it
```

**Step 3:** Restart the application. The Planner automatically discovers it. No graph changes. No configuration files.

---

## 6. Execution Flow Examples

### 6.1 Simple Query: "What is the schema of customers.users?"

```
Coordinator: Simple factual query. Delegating lightweight.
Planner: Single agent task -> Catalog Scout
Dispatcher: Send(Catalog Scout)
Blackboard: [Schema details]
Critic: Single finding, high confidence -> AUTO_APPROVE
Coordinator: 'Here is the schema of customers.users...'
```

**No human gate. No theater needed. Just fast answer.**

### 6.2 Complex Task: "Audit customers db and fix governance gaps"

```
Coordinator: Complex governance task. Full swarm deployment.
Planner: Decomposes into 6 subtasks across 4 agents
Dispatcher: Parallel Group 1 -> Scout + Steward
           Parallel Group 2 -> Guardian + Enforcer (after Group 1)
           Sequential -> Doc Expert (after Group 2)
           Sequential -> Critic (after all)
Blackboard: 12 findings, 2 conflicts
Critic: 1 conflict resolved (Steward vs Enforcer on ssn)
        1 conflict escalated (Guardian anomaly needs human review)
        8 actions approved, 2 escalated
Human Gate: Slack notification with approval buttons
Action Executor: Executes 8 approved actions via MCP
Coordinator: 'Swarm complete. 8 actions applied, 2 need your review...'
```

### 6.3 Conflict Scenario: "Tag all email columns as PII"

```
Data Steward: Proposes tagging 15 email columns as PII.Sensitive
Policy Enforcer: Flags 3 columns in `public_marketing` database
                 -> 'Marketing email lists have different legal basis'
                 -> Proposes PII.Internal instead
                 
Blackboard Conflict:
  Finding A (Steward): `public_marketing.leads.email` -> PII.Sensitive
  Finding B (Enforcer): `public_marketing.leads.email` -> PII.Internal
  
Integrity Critic:
  - Checks policy document: Marketing consented emails -> Internal
  - Checks legal precedent: 3 similar cases resolved as Internal
  - Resolution: Override Steward for `public_marketing.*`
  - Confidence: 0.96
  
Final: 12 columns -> PII.Sensitive, 3 columns -> PII.Internal
```

---

## 7. Technical Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Orchestration | LangGraph | Sequential execution via Supervisor pattern, state management, human-in-the-loop interrupts |
| LLM Framework | LangChain | Tool binding, structured output, multiple provider support |
| State Persistence | PostgreSQL + LangGraph PostgresSaver | Recovery from crashes, audit trails, multi-instance support |
| Real-time Streaming | WebSocket (FastAPI) + Server-Sent Events | Live theater updates without polling |
| Frontend | Streamlit | Rapid prototyping, built-in widgets, easy deployment |
| Chat Integrations | Slack Bolt + Microsoft Teams Bot Framework | Native threading, interactive blocks |
| MCP Client | OpenMetadata native MCP | First-class protocol support, not wrapper |
| Configuration | Pydantic Settings | Type-safe, env-var based, validation |
| Observability | OpenTelemetry + Structured JSON Logs | Distributed tracing, agent metrics, cost attribution |

---

## 8. Open Questions for Debate

Here are the architectural tensions I want to debate:

### Q1: Should the Coordinator be an LLM or a rules engine?
- **LLM argument:** Natural conversation, context understanding, handles edge cases
- **Rules engine argument:** Deterministic, faster, cheaper, easier to test
- **Hybrid proposal:** Rules engine for routing decisions, LLM for response generation

### Q2: How much should the Planner use LLM vs. deterministic planning?
- **LLM planning:** Handles novel tasks, creative decomposition
- **Deterministic:** Reliable, reproducible, no hallucinated subtasks
- **Current approach:** LLM generates plan, then validate against agent capabilities

### Q3: Should agents share an LLM instance or have dedicated models?
- **Shared:** Consistent behavior, easier to manage
- **Dedicated:** Each agent can use optimal model (cheap for Scout, powerful for Critic)
- **Current approach:** Configurable per-agent with tiered strategy

### Q4: Blackboard: Event log vs. queryable knowledge graph?
- **Event log:** Simple, append-only, proven pattern
- **Knowledge graph:** Rich relationships, inference, but complex
- **Current approach:** Event log with entity indexing for queries

### Q5: Human gate: Per-action or per-batch?
- **Per-action:** Fine-grained control, tedious for bulk operations
- **Per-batch:** Efficient, risk of missing bad actions
- **Current approach:** Configurable threshold (auto-approve if confidence > 0.95 and no conflicts)

### Q6: Should the swarm be able to self-modify? (Add agents, change plans)
- **Yes:** True autonomy, emergent behavior
- **No:** Predictability, safety, easier to debug
- **Current approach:** Planner can replan based on findings, but cannot add new agent types

---

## 9. Success Metrics for Hackathon Judging

| Dimension | How We Demonstrate |
|-----------|-------------------|
| **Innovation** | First multi-agent swarm with dynamic composition on MCP |
| **Technical Depth** | Live blackboard, conflict resolution, idempotent execution |
| **Practical Utility** | Real OpenMetadata instance, real MCP calls, real metadata changes |
| **Extensibility** | Add `CostOptimizer` agent live during demo |
| **User Experience** | Natural language in, orchestrated swarm out, human approves |
| **Robustness** | Kill an agent mid-run, show swarm recovery |