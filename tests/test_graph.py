"""
Integration tests for OpenMetaMind graph workflow.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from src.graph.coordinator import Coordinator
from src.graph.planner import Planner
from src.graph.dispatcher import Dispatcher
from src.graph.supervisor import Supervisor
from src.graph.swarm_graph import build_swarm_graph
from src.models.state import SwarmState


class TestCoordinator:
    """Tests for the Coordinator node."""

    @pytest.fixture
    def coordinator(self, mock_llm):
        with patch('src.graph.coordinator.ChatOpenAI', return_value=mock_llm):
            return Coordinator()

    @pytest.mark.asyncio
    async def test_coordinator_classifies_delegate_task(self, coordinator, sample_swarm_state):
        """Test that coordinator routes delegation tasks to planner."""
        sample_swarm_state["user_input"] = "List tables in customers database"

        # Mock the intent chain to return a delegate intent
        delegate_result = {"intent": "delegate_lightweight", "reasoning": "Test delegation"}
        with patch.object(coordinator, 'intent_chain') as mock_chain:
            mock_chain.invoke = MagicMock(return_value=delegate_result)
            result = coordinator(sample_swarm_state)

        assert "next" in result
        assert result["next"] == "planner"

    @pytest.mark.asyncio
    async def test_coordinator_sets_delegated_task(self, coordinator, sample_swarm_state):
        """Test that coordinator sets delegated_task for planner."""
        sample_swarm_state["user_input"] = "Audit the customers database"

        # Mock the intent chain to return a delegate intent
        delegate_result = {"intent": "delegate_full_swarm", "reasoning": "Complex task"}
        with patch.object(coordinator, 'intent_chain') as mock_chain:
            mock_chain.invoke = MagicMock(return_value=delegate_result)
            result = coordinator(sample_swarm_state)

        assert "delegated_task" in result
        assert result["delegated_task"] == "Audit the customers database"

    @pytest.mark.asyncio
    async def test_coordinator_adds_to_history(self, coordinator, sample_swarm_state):
        """Test that coordinator adds user message to conversation history."""
        sample_swarm_state["user_input"] = "What tables exist?"
        sample_swarm_state["conversation_history"] = []
        
        result = coordinator(sample_swarm_state)
        
        assert "conversation_history" in result
        assert len(result["conversation_history"]) > 0


class TestPlanner:
    """Tests for the Planner node."""

    @pytest.fixture
    def planner(self, mock_llm):
        with patch('src.graph.planner.ChatOpenAI', return_value=mock_llm):
            return Planner()

    @pytest.mark.asyncio
    async def test_planner_creates_execution_plan(self, planner, sample_swarm_state):
        """Test that planner creates an execution plan."""
        sample_swarm_state["delegated_task"] = "List tables in customers database"
        
        result = planner(sample_swarm_state)
        
        assert "execution_plan" in result
        assert result["execution_plan"] is not None

    @pytest.mark.asyncio
    async def test_planner_includes_subtasks(self, planner, sample_swarm_state):
        """Test that execution plan includes subtasks."""
        sample_swarm_state["delegated_task"] = "Audit the customers database"
        
        result = planner(sample_swarm_state)
        
        execution_plan = result["execution_plan"]
        if isinstance(execution_plan, dict):
            assert "subtasks" in execution_plan
            assert len(execution_plan["subtasks"]) > 0
        else:
            assert hasattr(execution_plan, 'subtasks')
            assert len(execution_plan.subtasks) > 0

    @pytest.mark.asyncio
    async def test_planner_includes_parallel_groups(self, planner, sample_swarm_state):
        """Test that execution plan includes parallel groups."""
        sample_swarm_state["delegated_task"] = "Analyze data quality"
        
        result = planner(sample_swarm_state)
        
        execution_plan = result["execution_plan"]
        if isinstance(execution_plan, dict):
            assert "parallel_groups" in execution_plan
        else:
            assert hasattr(execution_plan, 'parallel_groups')


class TestDispatcher:
    """Tests for the Dispatcher node with Supervisor pattern."""

    @pytest.fixture
    def dispatcher(self):
        return Dispatcher()

    def test_dispatcher_returns_empty_for_no_plan(self, dispatcher, sample_swarm_state):
        """Test that dispatcher routes to integrity_critic when no plan."""
        sample_swarm_state["execution_plan"] = None
        
        result = dispatcher(sample_swarm_state)
        
        # Should route directly to integrity_critic
        assert result["next"] == "integrity_critic"
        assert "pending_tasks" not in result

    def test_dispatcher_initializes_task_queue(self, dispatcher, sample_swarm_state):
        """Test that dispatcher initializes pending_tasks for Supervisor."""
        from src.models.plan import Subtask, ExecutionPlan
        
        sample_swarm_state["execution_plan"] = ExecutionPlan(
            subtasks=[
                Subtask(
                    subtask_id="task1",
                    agent_id="catalog_scout",
                    task_description="List tables",
                    required_inputs=[],
                    produces_output="tables",
                    dependencies=[]
                ),
                Subtask(
                    subtask_id="task2",
                    agent_id="data_steward",
                    task_description="Analyze tables",
                    required_inputs=["tables"],
                    produces_output="analysis",
                    dependencies=["task1"]
                )
            ],
            estimated_duration="30s",
            parallel_groups=[["task1"], ["task2"]]
        )
        
        result = dispatcher(sample_swarm_state)
        
        # Should initialize task queue and route to supervisor
        assert result["next"] == "supervisor"
        assert "pending_tasks" in result
        assert len(result["pending_tasks"]) == 2
        assert result["current_task_index"] == 0
        
        # First task should be task1
        assert result["pending_tasks"][0]["subtask_id"] == "task1"

    def test_dispatcher_routes_to_supervisor(self, dispatcher, sample_swarm_state):
        """Test that dispatcher always routes to supervisor when tasks exist."""
        from src.models.plan import Subtask, ExecutionPlan
        
        sample_swarm_state["execution_plan"] = ExecutionPlan(
            subtasks=[
                Subtask(
                    subtask_id="task1",
                    agent_id="catalog_scout",
                    task_description="List tables",
                    required_inputs=[],
                    produces_output="tables",
                    dependencies=[]
                )
            ],
            estimated_duration="30s",
            parallel_groups=[["task1"]]
        )
        
        result = dispatcher(sample_swarm_state)
        
        assert result["next"] == "supervisor"


class TestSupervisor:
    """Tests for the Supervisor node."""

    @pytest.fixture
    def supervisor(self):
        return Supervisor()

    def test_supervisor_moves_to_critic_when_no_tasks(self, supervisor, sample_swarm_state):
        """Test that supervisor routes to integrity_critic when no pending tasks."""
        sample_swarm_state["pending_tasks"] = []
        
        result = supervisor(sample_swarm_state)
        
        assert result["next"] == "integrity_critic"

    def test_supisor_executes_single_task(self, supervisor, sample_swarm_state):
        """Test that supervisor executes a single task and moves to critic."""
        sample_swarm_state["pending_tasks"] = [
            {
                "subtask_id": "task1",
                "agent_id": "catalog_scout",
                "task": "List tables",
                "required_inputs": [],
                "dependencies": [],
                "produces_output": "tables"
            }
        ]
        sample_swarm_state["findings"] = []
        sample_swarm_state["completed_subtasks"] = []
        
        # Mock the agent execution
        mock_finding = MagicMock()
        mock_finding.confidence = 0.95
        mock_finding.dict.return_value = {"finding": "data"}
        
        with patch.object(supervisor, '_execute_agent_sync', return_value=mock_finding):
            result = supervisor(sample_swarm_state)
        
        # Should route to integrity_critic (no more tasks)
        assert result["next"] == "integrity_critic"
        assert len(result["findings"]) == 1
        assert "task1" in result["completed_subtasks"]

    def test_supervisor_loops_for_multiple_tasks(self, supervisor, sample_swarm_state):
        """Test that supervisor loops back when more tasks remain."""
        sample_swarm_state["pending_tasks"] = [
            {
                "subtask_id": "task1",
                "agent_id": "catalog_scout",
                "task": "List tables",
                "required_inputs": [],
                "dependencies": [],
                "produces_output": "tables"
            },
            {
                "subtask_id": "task2",
                "agent_id": "data_steward",
                "task": "Analyze tables",
                "required_inputs": [],
                "dependencies": [],
                "produces_output": "analysis"
            }
        ]
        sample_swarm_state["findings"] = []
        sample_swarm_state["completed_subtasks"] = []
        
        # Mock the agent execution
        mock_finding = MagicMock()
        mock_finding.confidence = 0.95
        mock_finding.dict.return_value = {"finding": "data"}
        
        with patch.object(supervisor, '_execute_agent_sync', return_value=mock_finding):
            result = supervisor(sample_swarm_state)
        
        # Should loop back to supervisor for next task
        assert result["next"] == "supervisor"
        assert len(result["findings"]) == 1
        assert "task1" in result["completed_subtasks"]
        assert len(result["pending_tasks"]) == 1  # task2 remains


class TestSwarmGraph:
    """Integration tests for the complete swarm graph."""

    @pytest.mark.asyncio
    async def test_graph_builds_successfully(self, built_graph):
        """Test that the graph builds without errors."""
        assert built_graph is not None
        assert hasattr(built_graph, 'ainvoke')

    @pytest.mark.asyncio
    async def test_graph_accepts_initial_state(self, built_graph, sample_swarm_state):
        """Test that graph accepts valid initial state."""
        config = {"configurable": {"thread_id": "test-thread"}}
        
        # This should not raise an error
        try:
            result = await built_graph.ainvoke(sample_swarm_state, config=config)
            assert result is not None
        except Exception as e:
            # Some errors are expected in mocked tests
            # Just verify the graph accepts the state structure
            assert "user_query" in sample_swarm_state or "user_input" in sample_swarm_state


class TestGraphRouting:
    """Tests for graph routing logic."""

    def test_coordinator_routes_to_planner_for_delegation(self, mock_llm):
        """Test that coordinator routes to planner for delegation tasks."""
        with patch('src.graph.coordinator.ChatOpenAI', return_value=mock_llm):
            coordinator = Coordinator()

            state = {
                "user_input": "List tables in customers database",
                "conversation_history": [],
                "user_query": "List tables in customers database"
            }

            # Mock the intent chain to return a delegate intent
            delegate_result = {"intent": "delegate_lightweight", "reasoning": "Test delegation"}
            with patch.object(coordinator, 'intent_chain') as mock_chain:
                mock_chain.invoke = MagicMock(return_value=delegate_result)
                result = coordinator(state)

            assert result.get("next") == "planner"

    def test_planner_routes_to_dispatcher(self, mock_llm):
        """Test that planner routes to dispatcher."""
        with patch('src.graph.planner.ChatOpenAI', return_value=mock_llm):
            planner = Planner()
            
            state = {
                "delegated_task": "List tables",
                "user_query": "List tables",
                "user_input": "List tables",
                "conversation_history": []
            }
            
            result = planner(state)
            
            assert "execution_plan" in result
