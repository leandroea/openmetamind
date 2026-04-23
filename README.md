# OpenMetaMind

Autonomous multi-agent swarm for OpenMetadata data governance using LangGraph.

## Project Structure

- `src/` - Source code
  - `graph/` - LangGraph workflow definitions (Coordinator, Planner, Dispatcher, Agent Executor, Integrity Critic, Action Executor)
  - `agents/` - SwarmAgent implementations (plugin system)
  - `mcp/` - OpenMetadata MCP client wrappers
  - `ui/` - Streamlit and Slack interfaces
  - `config/` - Configuration management
  - `models/` - Pydantic models and schemas
- `tests/` - Unit and integration tests
- `openmetamind_specification.md` - Detailed technical specification

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -e .
   ```
4. Copy `.env.example` to `.env` and fill in the required values:
   - `OPENMETADATA_MCP_URL`: URL of your OpenMetadata MCP server
   - `OPENMETADATA_JWT_TOKEN`: JWT token for authenticating with OpenMetadata MCP server
   - `NVIDIA_API_KEY`: API key for NVIDIA's LLM API (OpenAI-compatible)
   - `DATABASE_URL`: Connection string for the application's database (e.g., SQLite, PostgreSQL)
   - `SLACK_BOT_TOKEN`: Token for Slack bot (if using Slack integration)
   - `SLACK_SIGNING_SECRET`: Secret for Slack request verification
   - `SLACK_APP_TOKEN`: App-level token for Socket Mode (if using Slack integration)
   - `LOG_LEVEL`: Logging level (e.g., INFO, DEBUG)

5. Run the application:
   - For FastAPI backend: `uvicorn src.main:app --reload`
   - For Streamlit UI: `streamlit run src/ui/streamlit_app.py`
   - For Slack bot: `python src/ui/slack_bot.py`

## Dependencies

See `pyproject.toml` for the full list.

## Development

- Run tests: `pytest tests/`
- Run tests with coverage: `pytest tests/ --cov=src`
- Format code: `black src`
- Lint code: `ruff check src`
- Type check: `mypy src`

## Demo Data

To populate OpenMetadata with demo data for testing:

```bash
# Set environment variables
export OPENMETADATA_JWT_TOKEN=your_token_here
export CREATE_REAL_DATA=true  # Set to true to create real data

# Run the demo data script
python scripts/demo_data.py
```

## Architecture

The OpenMetaMind swarm follows this flow:

1. **Coordinator** - User's single point of contact, classifies intent
2. **Planner** - Decomposes tasks, selects agents, creates execution plan
3. **Dispatcher** - Spawns agents in parallel using LangGraph Send API
4. **Agent Executors** - Execute tasks using real MCP calls to OpenMetadata
5. **Integrity Critic** - Validates findings, detects conflicts, makes routing decisions
6. **Action Executor** - Performs MCP write operations (only component with write permissions)

## License

MIT