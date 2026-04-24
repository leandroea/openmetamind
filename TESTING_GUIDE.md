# OpenMetaMind Testing Guide

This guide provides step-by-step instructions to test the OpenMetaMind project.

## Prerequisites
- Python 3.13+ virtual environment (`.venv`) with dependencies installed
- `.env` file configured with API keys (MINIMAX_API_KEY, OPENMETADATA_MCP_URL, etc.)

---

## Step 1: Verify Environment Setup

### 1.1 Check Python Version
```cmd
.venv\Scripts\python --version
```
Expected: Python 3.13+

### 1.2 Verify Dependencies are Installed
```cmd
.venv\Scripts\pip list
```

### 1.3 Verify .env File Exists
```cmd
dir .env
```

---

## Step 2: Syntax and Import Checks

Verify all Python modules can be imported without errors.
**Important:** The `.env` file must be loaded first for MINIMAX_API_KEY.

### 2.1 Test Core Module Imports
```cmd
.venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv(); from src.config import Settings, get_settings; print('Config OK')"
```

### 2.2 Test Model Imports
```cmd
.venv\Scripts\python -c "from src.models.state import SwarmState; from src.models.plan import ExecutionPlan; print('Models OK')"
```

### 2.3 Test Agent Imports
```cmd
.venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv(); from src.agents.registry import AgentRegistry; print('Agents OK')"
```

### 2.4 Test Graph Imports
```cmd
.venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv(); from src.graph.swarm_graph import build_swarm_graph; print('Graph OK')"
```

---

## Step 3: Run Unit Tests

The test suite uses `conftest.py` at the project root to load `.env` before imports.

### 3.1 Run All Tests
```cmd
.venv\Scripts\python -m pytest tests/ -v
```

### 3.2 Run Tests by Category
```cmd
.venv\Scripts\python -m pytest tests/test_agents.py -v
.venv\Scripts\python -m pytest tests/test_graph.py -v
.venv\Scripts\python -m pytest tests/test_critic.py -v
```

### 3.3 Run with Coverage
```cmd
.venv\Scripts\python -m pytest tests/ --cov=src --cov-report=term
```

---

## Step 4: Test Individual Components

### 4.1 Test Agent Registry
```cmd
.venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv(); from src.agents.registry import AgentRegistry; r = AgentRegistry(); print(f'Agents: {[a.name for a in r.list_agents()]}')"
```

### 4.2 Test Settings Loading
```cmd
.venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv(); from src.config import get_settings; s = get_settings(); print(f'LLM Model: {s.llm_model}')"
```

---

## Step 5: Run Full Application

### 5.1 Start Streamlit UI
The FastAPI backend is no longer required - Streamlit calls the swarm directly via `SwarmRunner`.

```cmd
.venv\Scripts\python -m streamlit run src/ui/streamlit_app.py
```

Access the UI at `http://localhost:8501`

---

## Bug Fixes Applied During Testing

The following issues were discovered and fixed during the testing process:

1. **Missing `BaseMessage` import** in [`src/models/state.py`](src/models/state.py:14) — Added `from langchain_core.messages import BaseMessage`

2. **Missing model classes** in [`src/models/state.py`](src/models/state.py:101) — Added `CriticDecision`, `FindingAssessment`, and `CriticReview` classes that were imported by `integrity_critic.py` but not defined

3. **Wrong import path** in [`src/graph/swarm_graph.py`](src/graph/swarm_graph.py:14) — Changed `from .state import SwarmState` to `from ..models.state import SwarmState`

4. **Missing `langgraph-checkpoint-sqlite`** in [`requirements.txt`](requirements.txt:3) — Added the separate checkpoint package

5. **Outdated checkpointer** in [`tests/conftest.py`](tests/conftest.py:10) — Changed `SqliteSaver.from_conn_string(":memory:")` to `MemorySaver()` (new LangGraph API)

6. **MagicMock incompatibility** in [`tests/test_critic.py`](tests/test_critic.py:165) — Replaced `MagicMock()` with proper `MCPToolCall` instances for pydantic validation

7. **Coordinator test mocking** in [`tests/test_graph.py`](tests/test_graph.py:25) — Fixed mock LLM chain pattern to properly mock `intent_chain.invoke()` instead of the raw LLM

8. **Async context manager** in [`tests/test_agents.py`](tests/test_agents.py:69) — Added `__aenter__`/`__aexit__` mocks for the MCP client

9. **Root conftest.py** — Created [`conftest.py`](conftest.py) at project root to load `.env` before test collection

10. **Relative import errors** in [`src/ui/streamlit_app.py`](src/ui/streamlit_app.py:133) — Changed relative imports to absolute (`from src.ui.swarm_runner import ...`) for standalone execution via `streamlit run`

11. **Coordinator clarification issue** — Updated `intent_prompt` to properly classify OpenMetadata queries as `delegate_lightweight` instead of `clarify`

---
## Architecture Notes

**Supervisor/Manager Pattern:** Agents execute sequentially via the Supervisor node, not in parallel. This eliminates concurrent state update conflicts and simplifies debugging.

**Direct Swarm Execution:** Streamlit calls `SwarmRunner.run()` directly without going through an HTTP API. The `SwarmRunner` is imported via `from src.ui.swarm_runner import get_swarm_runner`.

**No API Between Agents:** After the refactoring, agents communicate via shared state (blackboard) rather than HTTP API calls. This simplifies deployment and improves reliability.

---

## Test Results

**50 passed, 0 failed** (as of latest run)
