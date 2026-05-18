# OpenMetaMind: Technical Specification
## Autonomous Multi-Agent Swarm for OpenMetadata Data Governance

---

## 1. Core Philosophy

**Thesis:** Data governance is not a single task performed by a single AI. It is a distributed cognitive process requiring multiple specialists who investigate, validate, and execute — just like a human data governance team.

**Anti-Thesis (what we reject):**
- Single-chatbot approaches (ChatGPT with a governance prompt)
- Black-box AI that makes changes without showing its work
- Hardcoded agent teams that require code changes to evolve

---

## 2. Architectural Principles

| Principle | Manifestation |
|-----------|---------------|
| **Swarm over Singleton** | Multiple independent agents with distinct roles |
| **Visible Cognition** | Every agent's reasoning is displayed |
| **Extensibility by Addition** | New agents are drop-in plugins |
| **Native Protocol** | All operations via OpenMetadata MCP server using langchain-mcp-adapters |

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
User Input
     │
     ▼
Orchestrator (src/orchestrator/orchestrator.py)
     │
     ▼
Dispatcher (src/orchestrator/dispatcher.py)
     │
     ▼
┌─────────────────────────────────────────┐
│         Specialized Agents              │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Catalog     │  │ Data Steward    │   │
│  │ Scout       │  │                 │   │
│  └─────────────┘  └─────────────────┘   │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Quality     │  │ Documentation   │   │
│  │ Guardian    │  │ Agent           │   │
│  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────┘
     │
     ▼
MCP via langchain-mcp-adapters
     │
     ▼
OpenMetadata MCP Server
```

### 3.2 Component Descriptions

#### Orchestrator (`src/orchestrator/orchestrator.py`)
Main entry point that manages the agent execution workflow.
- Routes tasks to appropriate agents based on task type
- Coordinates multi-agent workflows
- Synthesizes agent responses

#### Dispatcher (`src/orchestrator/dispatcher.py`)
Routes tasks to appropriate agents based on capabilities.
- Task queue management
- Execution ordering

#### Agents (`src/agents/`)
All agents inherit from `SwarmAgent` base class and use LangGraph's `create_agent` with native MCP tools.

### 3.3 MCP Integration

#### Native Client (`src/mcp/native_client.py`)
Uses `langchain-mcp-adapters` for native LangGraph integration:
- `MultiServerMCPClient` for async tool loading
- Dynamic tool discovery from OpenMetadata MCP server
- Streamable HTTP transport support

#### Legacy Client (`src/mcp/client.py`)
Provides direct JSON-RPC 2.0 communication:
- Async context manager for resource management
- Automatic retry with exponential backoff
- Error parsing and transformation

---

## 4. Available Agents

### 4.1 Catalog Scout
**File:** `src/agents/catalog_scout.py`
**Emoji:** 🔍

Discovery specialist that maps the OpenMetadata landscape.

**Capabilities:**
- Search for entities across the catalog
- Get detailed entity information
- Retrieve entity lineage
- Semantic search (when vector embeddings enabled)

### 4.2 Data Steward
**File:** `src/agents/data_steward.py`
**Emoji:** 🛡️

Classification specialist for PII detection, tag assignment, and ownership.

**Capabilities:**
- Detect personally identifiable information
- Assign governance tags
- Manage asset ownership

### 4.3 Quality Guardian
**File:** `src/agents/quality_guardian.py`
**Emoji:** ⚖️

Quality analyst for profiling tables and detecting anomalies.

**Capabilities:**
- Profile tables with statistical metrics
- Detect anomalies in data
- Assess overall data quality

### 4.4 Documentation Agent
**File:** `src/agents/documentation_agent.py`
**Emoji:** 📝

Metadata specialist for documenting undocumented entities.

**Capabilities:**
- Find undocumented entities
- Generate business-friendly descriptions
- Full documentation pipeline

---

## 5. Agent Implementation Pattern

All agents follow the same implementation pattern using LangGraph:

```python
class AgentName:
    SYSTEM_PROMPT = """Agent instructions with MCP tool descriptions."""

    def __init__(self):
        settings = get_settings()
        self.llm = settings.create_llm_client(temperature=0.1)
        self._agent = None

    async def _get_agent(self):
        if self._agent is None:
            tools = await get_mcp_tools_async()
            self._agent = create_agent(
                self.llm, 
                tools, 
                system_prompt=self.SYSTEM_PROMPT
            )
        return self._agent

    async def execute(self, task: str, inputs: Dict) -> str:
        agent = await self._get_agent()
        # Execute with streaming
        result_messages = []
        async for chunk in agent.astream(input_data, stream_mode="messages"):
            result_messages.append(chunk)
        # Accumulate and return response
        return accumulate_response(result_messages)
```

---

## 6. MCP Tools

The OpenMetadata MCP server provides these tools:

| Tool | Description |
|------|-------------|
| `search_metadata` | Search across all metadata entities |
| `get_entity_details` | Get detailed entity information |
| `create_glossary` | Create a new glossary |
| `create_glossary_term` | Create a glossary term |
| `get_entity_lineage` | Get upstream/downstream lineage |
| `semantic_search` | AI-powered semantic search |
| `create_lineage` | Create lineage edges |
| `patch_entity` | Update entity metadata |
| `get_test_definitions` | List data quality tests |
| `create_test_case` | Create test cases |
| `root_cause_analysis` | Analyze quality failures |

---

## 7. Project Structure

```
openmetamind/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── orchestrator.py
│   │   ├── catalog_scout.py
│   │   ├── data_steward.py
│   │   ├── quality_guardian.py
│   │   └── documentation_agent.py
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   └── dispatcher.py
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── native_client.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── streamlit_app.py
│   │   ├── swarm_runner.py
│   │   └── slack_bot.py
│   └── config/
│       ├── __init__.py
│       ├── settings.py
│       └── logging.py
├── tests/
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 8. Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.10+ |
| Multi-Agent Framework | LangGraph |
| MCP Integration | langchain-mcp-adapters |
| LLM Integration | LangChain + MiniMax |
| Data Validation | Pydantic v2 |
| User Interface | Streamlit |
| Testing | pytest, pytest-asyncio |

---

## 9. Adding New Agents

1. Create a new file in `src/agents/` (e.g., `new_agent.py`)
2. Inherit from `SwarmAgent` base class
3. Implement required properties:
   - `agent_id`: Unique string identifier
   - `display_name`: Human-readable name
   - `description`: What the agent does
   - `avatar_emoji`: UI representation
   - `capabilities`: List of capability dicts
4. Implement `execute()` method
5. Import and register in `src/agents/__init__.py`
