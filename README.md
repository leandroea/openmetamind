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
| **MCP Integration** | langchain-mcp-adapters |
| **LLM Integration** | LangChain + MiniMax (OpenAI-compatible API) |
| **Data Validation** | Pydantic v2 |
| **Configuration** | Pydantic Settings + python-dotenv |
| **User Interface** | Streamlit |
| **Messaging (Optional)** | Slack Bolt |
| **Testing** | pytest, pytest-asyncio |
| **Code Quality** | Black, Ruff, MyPy |

---

## OpenMetadata MCP Integration

OpenMetaMind connects to OpenMetadata via its **MCP (Model Context Protocol) server**. Agents use **native LangGraph MCP integration** via [`langchain-mcp-adapters`](src/mcp/native_client.py:1) for seamless tool discovery and execution.

### MCP Server Tools (v1.13.x / AI SDK)

The following tools are available via the OpenMetadata MCP server:

| Tool | Description | Category |
|------|-------------|----------|
| `search_metadata` | Search across all metadata (tables, dashboards, etc.) | Discovery |
| `get_entity_details` | Retrieve detailed information for a specific entity | Entity |
| `create_glossary` | Create a new glossary | Glossary |
| `create_glossary_term` | Create a new term within an existing glossary | Glossary |
| `get_entity_lineage` | Retrieve upstream and downstream lineage | Lineage |
| `semantic_search` | AI-powered semantic search beyond keyword matching | Discovery |
| `create_lineage` | Create a lineage edge between two entities | Lineage |
| `patch_entity` | Update an entity's metadata (description, tags, owners) | Entity |
| `get_test_definitions` | List available data quality test definitions | Quality |
| `create_test_case` | Create a data quality test case for an entity | Quality |
| `root_cause_analysis` | Analyze root causes of data quality failures | Quality |

**Note:** `patch_entity` with JSONPatch operations handles description updates, tag additions/removals, and owner management.

### Native MCP Client

The [`NativeMCPClient`](src/mcp/native_client.py:1) class provides:
- Native LangGraph integration via `langchain-mcp-adapters`
- `MultiServerMCPClient` for async tool loading
- Dynamic tool discovery from MCP server
- Streamable HTTP transport support

### Authentication

MCP uses JWT Bearer authentication:
- `OPENMETADATA_MCP_URL`: MCP server endpoint URL
- `OPENMETADATA_JWT_TOKEN`: JWT token for authentication

---

## System Architecture

OpenMetaMind uses **LangGraph with native MCP integration** for multi-agent orchestration. The architecture follows a **agent-based pattern** where the orchestrator routes tasks to specialized agents.

### Core Architecture

```
User Input
     │
     ▼
Orchestrator ([src/agents/orchestrator.py](src/agents/orchestrator.py:1))
     │
     ▼
┌─────────────────────────────────────────┐
│         Specialized Agents              │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │ Catalog     │  │ Data Steward    │  │
│  │ Scout       │  │                 │  │
│  └─────────────┘  └─────────────────┘  │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │ Quality     │  │ Documentation   │  │
│  │ Guardian    │  │ Agent           │  │
│  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────┘
     │
     ▼
Result/Response to User
```

### MCP Integration

All agents use **native LangGraph MCP integration** via [`langchain-mcp-adapters`](src/mcp/native_client.py:1). This provides:
- Dynamic tool discovery from OpenMetadata MCP server
- Async tool execution with proper streaming
- Type-safe tool call handling

### Core Components

#### 1. Orchestrator ([`src/agents/orchestrator.py`](src/agents/orchestrator.py:1))
Main entry point that manages the agent execution workflow. Routes tasks to appropriate agents and synthesizes results.

#### 2. Agent Base ([`src/agents/base.py`](src/agents/base.py:1))
Abstract base class defining the agent interface. All agents inherit from this base class.

#### 3. Agent Registry ([`src/agents/registry.py`](src/agents/registry.py:1))
Discovers and registers available agents. Provides agent lookup by capability.

#### 4. Native MCP Client ([`src/mcp/native_client.py`](src/mcp/native_client.py:1))
Provides native LangGraph MCP integration using `langchain-mcp-adapters` `MultiServerMCPClient`.

### Agent Execution Pattern

Each agent uses LangGraph's `create_agent` with native MCP tools:

1. Agent receives task
2. MCP tools are loaded via `get_mcp_tools_async()`
3. LangGraph agent is created with system prompt
4. Agent executes using ReAct pattern with MCP tools
5. Results are streamed and accumulated

---

## Available Agents

OpenMetaMind ships with **four specialized governance agents**:

### 1. Catalog Scout ([`src/agents/catalog_scout.py`](src/agents/catalog_scout.py:1))
**Emoji**: 🔍 | **ID**: `catalog_scout`

The discovery specialist. Maps the OpenMetadata landscape by finding entities and understanding their structure.

| Capability | Description |
|------------|-------------|
| `search_metadata` | Search for entities across the OpenMetadata catalog |
| `get_entity_details` | Get detailed information about specific entities including columns |
| `get_entity_lineage` | Retrieve upstream and downstream lineage |
| `semantic_search` | AI-powered semantic search (when vector embeddings enabled) |

**Use cases**: Finding all tables in a database, discovering entities with specific tags, understanding catalog structure.

---

### 2. Data Steward ([`src/agents/data_steward.py`](src/agents/data_steward.py:1))
**Emoji**: 🛡️ | **ID**: `data_steward`

The classification specialist. Handles PII detection, tag assignment, and ownership management. Uses LangGraph with native MCP tools and MiniMax LLM for intelligent analysis.

| Capability | Description |
|------------|-------------|
| `pii_detection` | Detects personally identifiable information in columns using pattern matching and LLM analysis |
| `tag_assignment` | Assigns governance tags to entities based on content analysis |
| `ownership_management` | Suggests or assigns asset owners based on lineage and business context |

**Use cases**: Identifying PII columns, enforcing classification policies, ensuring ownership metadata is complete.

---

### 3. Quality Guardian ([`src/agents/quality_guardian.py`](src/agents/quality_guardian.py:1))
**Emoji**: ⚖️ | **ID**: `quality_guardian`

The quality analyst. Profiles tables, detects anomalies, and validates SLAs.

| Capability | Description |
|------------|-------------|
| `table_profiling` | Profiles tables with statistical metrics |
| `anomaly_detection` | Detects anomalies in data distribution |
| `quality_assessment` | Assesses overall data quality score |

**Use cases**: Finding tables with quality issues, detecting data quality regressions, SLA compliance auditing.

---

### 4. Documentation Agent ([`src/agents/documentation_agent.py`](src/agents/documentation_agent.py:1))
**Emoji**: 📝 | **ID**: `documentation_agent`

The metadata specialist. Finds undocumented entities and generates business-friendly descriptions.

| Capability | Description |
|------------|-------------|
| `find_undocumented` | Identifies tables and columns missing descriptions |
| `generate_description` | Uses LLM to generate business-friendly descriptions from context |
| `document_entities` | Full pipeline: finds undocumented entities and proposes descriptions |

**Use cases**: Auditing documentation completeness, bulk-adding missing descriptions, explaining table structure to users.

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
   - `capabilities`: List of capability dictionaries
   - `execute()`: Async method returning task result

4. Import the agent in [`src/agents/__init__.py`](src/agents/__init__.py:1) to register it

The orchestrator automatically discovers agents via the Agent Registry.

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
| **Extensibility by Addition** | New agents are plugins, not core rewrites |
| **Human Sovereignty** | AI proposes, human approves all actions |
| **Native Protocol** | All operations via OpenMetadata MCP server using langchain-mcp-adapters |

---

## Future Improvements

The following enhancements are planned for future releases:

### High Priority
- **Policy Enforcer Agent**: Automated compliance checking against defined policies
- **Impact Analyst Agent**: Assess downstream effects of schema changes
- **Glossary Manager Agent**: Manage business glossary terms and relationships
- **Lineage Tracker Agent**: Track and visualize data lineage

### Medium Priority
- **Persistent Audit Trail**: Enhanced audit logging with search/filter
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
│   │   ├── __init__.py  # Agent registry and initialization
│   │   ├── base.py      # SwarmAgent abstract base class
│   │   ├── registry.py  # Agent discovery and registration
│   │   ├── orchestrator.py  # Main orchestrator for agent execution
│   │   ├── catalog_scout.py  # Discovery agent
│   │   ├── data_steward.py  # Governance agent
│   │   ├── quality_guardian.py  # Quality analysis agent
│   │   └── documentation_agent.py  # Documentation agent
│   ├── mcp/             # OpenMetadata MCP client
│   │   ├── __init__.py
│   │   ├── client.py  # MCP client utilities
│   │   └── native_client.py  # Native langchain-mcp-adapters integration
│   ├── ui/              # User interfaces
│   │   ├── __init__.py
│   │   ├── streamlit_app.py  # Streamlit web interface
│   │   ├── swarm_runner.py  # CLI swarm runner
│   │   └── slack_bot.py  # Slack integration
│   └── config/          # Configuration management
│       ├── __init__.py
│       ├── settings.py  # Pydantic settings
│       └── logging.py  # Logging configuration
├── tests/               # Unit and integration tests
├── openmetamind_specification.md  # Detailed technical specification
├── pyproject.toml
├── requirements.txt
└── README.md
```
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