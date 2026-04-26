# OpenMetaMind

**Autonomous multi-agent swarm for OpenMetadata data governance using LangGraph.**

OpenMetaMind is an AI-powered system that simulates a distributed data governance team. Instead of a single chatbot making all decisions, it uses multiple specialized agents that investigate, debate, validate, and execute governance tasks collaboratively. Every agent's reasoning is visible, every action is auditable, and every change requires human approval before execution.

---

## What is OpenMetaMind?

OpenMetaMind addresses a fundamental truth about data governance: **it's not a single task performed by a single AI**. Data governance is a distributed cognitive process requiring multiple specialists who investigate, debate, validate, and execute — just like a human data governance team.

Traditional approaches fail because they rely on:
- Single-chatbot approaches with a governance prompt
- Static workflow automation with AI sprinkled on top
- Black-box AI that makes changes without showing its work
- Hardcoded agent teams that require code changes to evolve

OpenMetaMind rejects all of these. It provides:

- **Visible Cognition**: Every agent's reasoning, findings, and conflicts are displayed in real-time
- **Dynamic Composition**: Agents self-assemble per task; no pre-built workflow templates
- **Extensibility by Addition**: New agents are drop-in plugins, not graph rewrites
- **Human Sovereignty**: AI proposes, human approves; the swarm serves, it does not replace
- **Native Protocol**: All operations flow through OpenMetadata's MCP server, not wrapper APIs

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.10+ |
| **Multi-Agent Framework** | LangGraph |
| **LLM Integration** | LangChain + MiniMax (OpenAI-compatible API) |
| **Data Validation** | Pydantic v2 |
| **Configuration** | Pydantic Settings + python-dotenv |
| **User Interface** | Streamlit |
| **Messaging (Optional)** | Slack Bolt |
| **Database** | SQLite (aiosqlite) |
| **Testing** | pytest, pytest-asyncio |
| **Code Quality** | Black, Ruff, MyPy |

---

## OpenMetadata MCP Integration

OpenMetaMind connects to OpenMetadata via its **MCP (Model Context Protocol) server**, which provides JSON-RPC 2.0 over HTTP with JWT Bearer authentication. All agents interact with OpenMetadata through the [`OpenMetadataMCPClient`](src/mcp/client.py:45) class.

### MCP Server Tools

The following tools are available via the MCP server:

#### Discovery & Search

| Tool | Description |
|------|-------------|
| `search_metadata` | Keyword-based search for data assets (tables, dashboards, etc.) |
| `search_metadata_all` | Paginated search returning all results with pagination handling |
| `semantic_search` | Vector embedding-based semantic search for meaning-based discovery |

#### Entity Operations

| Tool | Description |
|------|-------------|
| `get_entity_details` | Get detailed information about a specific entity by FQN |
| `patch_entity` | Patch an entity using JSONPatch operations (add/replace/remove fields) |
| `get_entity_lineage` | Get lineage information with configurable upstream/downstream depth |

#### Tagging & Classification

| Tool | Description |
|------|-------------|
| `add_tags` | Add tags to an entity (table, column, etc.) |
| `delete_tag` | Remove a tag from an entity |

#### Ownership & Descriptions

| Tool | Description |
|------|-------------|
| `update_description` | Update entity description (uses patch_entity internally) |
| `add_owner` | Add an owner to an entity (user or team) |
| `remove_owner` | Remove an owner from an entity |

#### Data Quality & Testing

| Tool | Description |
|------|-------------|
| `get_table_profile` | Get profile/statistics for a table (row count, size, etc.) |
| `create_test_case` | Create a test case for table or column |
| `get_test_definitions` | Get available test definitions |

#### Glossary & Lineage

| Tool | Description |
|------|-------------|
| `create_glossary` | Create a new glossary |
| `create_glossary_term` | Create a glossary term |
| `create_lineage` | Create lineage relationship between two entities |
| `root_cause_analysis` | Perform RCA via data quality lineage |

### Authentication

The MCP client uses JWT Bearer authentication:
- `OPENMETADATA_MCP_URL`: MCP server endpoint URL
- `OPENMETADATA_JWT_TOKEN`: JWT token for authentication

### Client Implementation

The [`OpenMetadataMCPClient`](src/mcp/client.py:45) class provides:
- Async context manager for proper resource management
- Automatic retry with exponential backoff for transient errors
- JSON-RPC 2.0 request/response handling
- Error parsing and transformation

---

## System Architecture

OpenMetaMind uses the **Supervisor/Manager pattern** for multi-agent orchestration. The Coordinator is the entry point that classifies user intent and decides whether to answer directly, delegate to the swarm, or ask for clarification. When delegation is needed, the flow proceeds through a sequential pipeline where tasks are executed one by one and results are synthesized before moving to the next phase.

The complete LangGraph workflow follows this sequence:

```
Coordinator (entry point)
    │
    ├─► END (answer directly / clarify / self-identity / team roster)
    │
    └─► Planner
             │
             ▼
        Dispatcher
             │
             ▼
        Supervisor ◄──┐ (loops while tasks remain)
             │        │
             ▼        │
    Integrity Critic  │ (after all tasks complete)
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
   END   Planner  Action Executor
  (human    (retry)    │
  approval)            ▼
                   END (execution complete)
```

### Node Flow Details

| From | To | Condition |
|------|-----|-----------|
| Coordinator | Planner | `next = "planner"` (delegate intent) |
| Coordinator | END | `next = "end"` (answer/clarify/self-identity/roster) |
| Planner | Dispatcher | Always (after creating execution plan) |
| Dispatcher | Supervisor | Always (initializes task queue) |
| Supervisor | Supervisor | `next = "supervisor"` (more tasks pending) |
| Supervisor | Integrity Critic | `next = "integrity_critic"` (all tasks done) |
| Integrity Critic | Action Executor | Auto-approve (high confidence) |
| Integrity Critic | Planner | Retry (low confidence, needs replanning) |
| Integrity Critic | END | Human gate (requires user approval) |
| Action Executor | END | Always (after executing proposed actions) |

### Supervisor Loop Pattern

The Supervisor iterates through tasks **sequentially** (not in parallel). After each task completes, the Supervisor updates the state and either loops back for the next task or moves to the Integrity Critic.

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

This sequential approach eliminates concurrent state update conflicts and makes debugging straightforward.

### Core Components

#### 1. Coordinator ([`src/graph/coordinator.py`](src/graph/coordinator.py:1))
The user's single point of contact. Maintains conversation memory and decides whether to:
- Answer directly from memory (follow-up questions)
- Delegate lightweight tasks (single agent, no critic)
- Delegate full swarm (planner + multi-agent + critic)
- Ask clarifying questions

#### 2. Planner ([`src/graph/planner.py`](src/graph/planner.py:1))
The "project manager" of the swarm. Decomposes tasks, queries the Agent Registry for suitable agents, and generates an execution DAG with task dependencies.

#### 3. Dispatcher ([`src/graph/dispatcher.py`](src/graph/dispatcher.py:1))
Initializes the task queue from the Planner's execution plan and sets up execution order for the Supervisor.

#### 4. Supervisor ([`src/graph/supervisor.py`](src/graph/supervisor.py:1))
The central orchestrator that iterates through tasks sequentially. After each agent completes, synthesizes results and decides whether to continue the loop or move to the Integrity Critic.

#### 5. Integrity Critic ([`src/graph/integrity_critic.py`](src/graph/integrity_critic.py:1))
Not just a validator — a true critic that reads the blackboard, detects contradictions, assigns final confidence, and decides routing:
- **AUTO_APPROVE**: High confidence, proceed directly to Action Executor
- **ESCALATE_TO_HUMAN**: Low confidence or conflicts, requires user approval
- **REJECT_AND_RETRY**: Invalid findings, send back to agents

#### 6. Action Executor ([`src/graph/action_executor.py`](src/graph/action_executor.py:1))
Performs actual MCP write operations. The only component with write permissions. Supports batch execution with rollback on failure and idempotency checks.

### Blackboard (Shared State)

The blackboard is an **append-only event log**, not a mutable shared dictionary. Every agent writes findings; no agent overwrites another. This ensures complete auditability.

---

## Available Agents

OpenMetaMind ships with **four specialized governance agents** plus an example agent for reference:

### 1. Catalog Scout ([`src/agents/catalog_scout.py`](src/agents/catalog_scout.py:1))
**Emoji**: 🔍 | **ID**: `catalog_scout`

The discovery specialist. Maps the OpenMetadata landscape by finding entities and understanding their structure.

| Capability | Description |
|------------|-------------|
| `list_entities` | Lists entities of a given type (tables, databases, etc.) from OpenMetadata |
| `search_catalog` | Searches for entities matching a query string |
| `get_entity_details` | Gets detailed information about a specific entity |

**Use cases**: Finding all tables in a database, discovering entities with specific tags, understanding catalog structure.

---

### 2. Data Steward ([`src/agents/data_steward.py`](src/agents/data_steward.py:1))
**Emoji**: 🛡️ | **ID**: `data_steward`

The classification specialist. Handles PII detection, tag assignment, and ownership management. Uses LangChain with MiniMax LLM for intelligent analysis.

| Capability | Description |
|------------|-------------|
| `pii_detection` | Detects personally identifiable information in columns using pattern matching and LLM analysis |
| `tag_assignment` | Assigns governance tags to entities based on content analysis |
| `ownership_management` | Suggests or assigns asset owners based on lineage and business context |

**Use cases**: Identifying PII columns, enforcing classification policies, ensuring ownership metadata is complete.

---

### 3. Quality Guardian ([`src/agents/quality_guardian.py`](src/agents/quality_guardian.py:1))
**Emoji**: 🔬 | **ID**: `quality_guardian`

The quality analyst. Profiles tables, detects anomalies, and validates SLAs.

| Capability | Description |
|------------|-------------|
| `profile_table` | Gathers quality metrics (null counts, uniqueness, distribution) for a table |
| `detect_anomalies` | Detects anomalies in data distribution compared to baseline profiles |
| `validate_sla` | Checks if table quality meets defined service level agreements |

**Use cases**: Finding tables with stale profiles, detecting data quality regressions, SLA compliance auditing.

---

### 4. Documentation Agent ([`src/agents/documentation_agent.py`](src/agents/documentation_agent.py:1))
**Emoji**: 📝 | **ID**: `documentation_agent`

The metadata specialist. Finds undocumented entities and generates business-friendly descriptions.

| Capability | Description |
|------------|-------------|
| `find_undocumented` | Identifies tables and columns missing descriptions |
| `generate_description` | Uses LLM to generate business-friendly descriptions from context |
| `document_entities` | Full pipeline: finds undocumented entities and proposes descriptions |
| `explain_structure` | Read-only mode that explains table structure without proposing changes |

**Use cases**: Auditing documentation completeness, bulk-adding missing descriptions, explaining table structure to users.

---

### 5. Example Agent ([`src/agents/example_agent.py`](src/agents/example_agent.py:1))
**Emoji**: 📚 | **ID**: `example_agent`

A reference implementation demonstrating the SwarmAgent interface. Used as a template for building new agents.

---

## Adding New Agents

New agents are **drop-in plugins**. To add an agent:

1. Create a new file in `src/agents/` (e.g., `policy_enforcer.py`)
2. Inherit from `SwarmAgent` base class
3. Implement the required properties and methods:
   - `agent_id`: Unique string identifier
   - `display_name`: Human-readable name
   - `description`: What the agent does
   - `avatar_emoji`: UI representation
   - `capabilities`: List of `Capability` objects
   - `can_handle()`: Lightweight task suitability check
   - `execute()`: Core logic returning `AgentFinding`

4. Import the agent in [`src/agents/__init__.py`](src/agents/__init__.py:1) to register it

The Planner automatically discovers agents via the Agent Registry.

---

## Setup and Installation

### Prerequisites

- Python 3.10+
- OpenMetadata MCP server running
- MiniMax API key (or OpenAI-compatible API key)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd openmetamind

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
OPENMETADATA_MCP_URL=http://localhost:8090    # MCP server URL
OPENMETADATA_JWT_TOKEN=your-jwt-token          # MCP authentication
MINIMAX_API_KEY=your-api-key                   # LLM API (OpenAI-compatible)

# Optional
DATABASE_URL=sqlite:///openmetamind.db         # Default: SQLite in project root
SLACK_BOT_TOKEN=xob-...                        # For Slack integration
SLACK_SIGNING_SECRET=...                        # Slack request verification
SLACK_APP_TOKEN=xapp-...                        # Slack Socket Mode
LOG_LEVEL=INFO                                 # DEBUG, INFO, WARNING, ERROR
```

### Running the Streamlit App

```bash
python -m streamlit run src/ui/streamlit_app.py
```

The Streamlit interface provides:
- **Chat Panel**: Interact with the Coordinator
- **Swarm Theater**: Real-time visualization of agent execution
- **Blackboard**: Live view of all findings
- **Action Approval**: Approve/reject/modify proposed actions

---

## Architecture Principles

| Principle | How It's Applied |
|-----------|------------------|
| **Swarm over Singleton** | Multiple independent agents with distinct roles |
| **Visible Cognition** | Every agent's reasoning displayed in real-time |
| **Dynamic Composition** | Agents self-assemble per task from the registry |
| **Extensibility by Addition** | New agents are plugins, not graph rewrites |
| **Human Sovereignty** | AI proposes, human approves all actions |
| **Native Protocol** | All operations via OpenMetadata MCP server |

---

## Future Improvements

The following enhancements are planned for future releases:

### High Priority
- **Policy Enforcer Agent**: Automated compliance checking against defined policies
- **Impact Analyst Agent**: Assess downstream effects of schema changes
- **Glossary Manager Agent**: Manage business glossary terms and relationships
- **Lineage Tracker Agent**: Track and visualize data lineage

### Medium Priority
- **Persistent Audit Trail**: Database-backed audit log with search/filter
- **Multi-language Support**: Interface localization for non-English users
- **Webhook Integration**: Notify external systems on action completion
- **Scheduled Governance Audits**: Automated periodic governance checks

### Lower Priority
- **Teams Integration**: Microsoft Teams bot alongside Slack
- **Advanced Visualizations**: D3.js-based lineage graphs, quality dashboards
- **Role-Based Access Control**: Different permissions for different user roles
- **Agent Performance Metrics**: Track agent accuracy over time

---

## Project Structure

```
openmetamind/
├── src/
│   ├── agents/          # SwarmAgent implementations (plugins)
│   │   ├── base.py      # SwarmAgent abstract base class
│   │   ├── registry.py  # Agent discovery and registration
│   │   ├── catalog_scout.py
│   │   ├── data_steward.py
│   │   ├── quality_guardian.py
│   │   ├── documentation_agent.py
│   │   └── example_agent.py
│   ├── graph/           # LangGraph workflow definitions
│   │   ├── coordinator.py
│   │   ├── planner.py
│   │   ├── dispatcher.py
│   │   ├── supervisor.py
│   │   ├── integrity_critic.py
│   │   ├── action_executor.py
│   │   └── swarm_graph.py
│   ├── mcp/             # OpenMetadata MCP client
│   │   └── client.py
│   ├── models/          # Pydantic models
│   │   └── state.py
│   ├── ui/              # User interfaces
│   │   ├── streamlit_app.py
│   │   ├── swarm_runner.py
│   │   └── slack_bot.py
│   └── config/          # Configuration management
│       ├── settings.py
│       └── logging.py
├── tests/               # Unit and integration tests
├── openmetamind_specification.md  # Detailed technical specification
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Development

```bash
# Run tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=src

# Format code
black src

# Lint code
ruff check src

# Type check
mypy src
```

---