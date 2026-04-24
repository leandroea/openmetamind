"""
Planner node for the OpenMetaMind swarm.

The Planner decomposes tasks into subtasks and selects appropriate agents.
It generates an ExecutionPlan with parallelization groups.
"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import os

from ..models.plan import Subtask, ExecutionPlan
from ..models.state import SwarmState
from ..agents.registry import AgentRegistry


class Planner:
    """
    The Planner node in the LangGraph workflow.
    
    Responsibilities:
    - Task decomposition and agent selection
    - Generate ExecutionPlan with subtasks and parallelization groups
    - Query Agent Registry for agent capabilities
    """

    def __init__(self):
        """Initialize the Planner with NVIDIA LLM."""
        # Initialize ChatOpenAI with NVIDIA endpoint
        nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        if not nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY must be set in environment variables")
        
        self.llm = ChatOpenAI(
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            api_key=nvidia_api_key,
            model=os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct"),
            temperature=0.1,
            max_tokens=1000
        )
        
        # Task decomposition prompt
        self.decomposition_prompt = ChatPromptTemplate.from_template(
            """You are the Planner for OpenMetaMind, an autonomous multi-agent swarm for OpenMetadata data governance.
            
            Your task is to decompose a user request into subtasks that can be executed by specialized agents.
            
            User request: {user_request}
            
            Available agents and their capabilities:
            {agent_capabilities}
            
            Decompose the request into subtasks. For each subtask, specify:
            1. subtask_id: Unique identifier (e.g., "discover_tables", "analyze_quality")
            2. agent_id: ID of the agent that should execute this subtask
            3. task_description: Natural language description of the subtask
            4. required_inputs: Keys from blackboard needed as inputs (e.g., ["table_list"])
            5. produces_output: Key that will be written to blackboard upon completion (e.g., "discovered_tables")
            6. dependencies: List of subtask_ids that must complete before this subtask can start
            7. max_retries: Maximum number of retry attempts (default: 2)
            8. timeout_seconds: Timeout in seconds for execution (default: 60)
            
            Group subtasks that can run in parallel into parallel_groups.
            
            Respond with a JSON object containing:
            {{
                "subtasks": [
                    {{
                        "subtask_id": "string",
                        "agent_id": "string",
                        "task_description": "string",
                        "required_inputs": ["string"],
                        "produces_output": "string",
                        "dependencies": ["string"],
                        "max_retries": 2,
                        "timeout_seconds": 60
                    }}
                ],
                "estimated_duration": "string (e.g., '45.2s')",
                "parallel_groups": [["subtask_id1", "subtask_id2"], ["subtask_id3"]]
            }}
            
            For now, use a simple heuristic decomposition:
            1. Discovery agents (catalog_scout) first to find entities
            2. Analysis agents (data_steward, quality_guardian) second to analyze findings
            3. Integrity critic last to validate results
            """
        )
        
        # Set up chain
        self.decomposition_chain = self.decomposition_prompt | self.llm | JsonOutputParser()

    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute the Planner node.
        
        Args:
            state: Current swarm state
            
        Returns:
            Dictionary with state updates
        """
        delegated_task = state.get("delegated_task", "")
        logger.info(f"Planner: Received delegated task: {delegated_task}")
        
        # Get available agents and their capabilities
        registry = AgentRegistry()
        agents = registry.list_agents()
        logger.info(f"Planner: Found {len(agents)} agents")
        
        # Format agent capabilities for the prompt
        agent_capabilities_str = ""
        for agent in agents:
            agent_capabilities_str += f"- {agent.display_name} ({agent.agent_id}): {agent.description}\n"
            if agent.capabilities:
                cap_names = [cap.name for cap in agent.capabilities]
                agent_capabilities_str += f"  Capabilities: {', '.join(cap_names)}\n"
        
        logger.info(f"Planner: Invoking decomposition chain for task: {delegated_task[:50]}...")
        
        # Decompose task into subtasks
        try:
            plan_result = self.decomposition_chain.invoke({
                "user_request": delegated_task,
                "agent_capabilities": agent_capabilities_str
            })
            
            logger.info(f"Planner: Decomposition successful, got {len(plan_result.get('subtasks', []))} subtasks")
            
            # Convert to ExecutionPlan object
            subtasks = [Subtask(**subtask_dict) for subtask_dict in plan_result.get("subtasks", [])]
            execution_plan = ExecutionPlan(
                subtasks=subtasks,
                estimated_duration=plan_result.get("estimated_duration", "unknown"),
                parallel_groups=plan_result.get("parallel_groups", [])
            )
            
        except Exception as e:
            logger.error(f"Planner: Decomposition failed: {str(e)}", exc_info=True)
            # Fallback to hardcoded decomposition if LLM fails
            logger.info("Planner: Using fallback plan")
            execution_plan = self._create_fallback_plan(delegated_task, agents)
        
        # Prepare state updates
        updates = {
            "execution_plan": execution_plan.dict() if hasattr(execution_plan, 'dict') else execution_plan,
            "completed_subtasks": [],  # Reset completed subtasks
            "current_parallel_group": []  # Will be set by dispatcher
        }
        
        logger.info(f"Planner: Returning with {len(updates['execution_plan']['subtasks'])} subtasks")
        
        return updates
    
    def _create_fallback_plan(
        self, 
        task: str, 
        agents: List[Any]
    ) -> ExecutionPlan:
        """
        Create a fallback execution plan when LLM decomposition fails.
        
        Uses a simple heuristic: discovery -> analysis -> validation
        """
        # Find agent instances
        agent_dict = {agent.agent_id: agent for agent in agents}
        
        subtasks = []
        
        # Subtask 1: Discovery (catalog_scout)
        if "catalog_scout" in agent_dict:
            subtasks.append(Subtask(
                subtask_id="discover_entities",
                agent_id="catalog_scout",
                task_description=f"Discover relevant entities for: {task}",
                required_inputs=[],
                produces_output="discovered_entities",
                dependencies=[],
                max_retries=2,
                timeout_seconds=60
            ))
        
        # Subtask 2: Data analysis (data_steward)
        if "data_steward" in agent_dict:
            subtasks.append(Subtask(
                subtask_id="analyze_data",
                agent_id="data_steward",
                task_description=f"Analyze data quality and classification for: {task}",
                required_inputs=["discovered_entities"],
                produces_output="analysis_results",
                dependencies=["discover_entities"],
                max_retries=2,
                timeout_seconds=120
            ))
        
        # Subtask 3: Quality analysis (quality_guardian)
        if "quality_guardian" in agent_dict:
            subtasks.append(Subtask(
                subtask_id="assess_quality",
                agent_id="quality_guardian",
                task_description=f"Assess data quality and detect anomalies for: {task}",
                required_inputs=["discovered_entities"],
                produces_output="quality_assessment",
                dependencies=["discover_entities"],
                max_retries=2,
                timeout_seconds=120
            ))
        
        # Subtask 4: Integrity critic (would be added in a real implementation)
        # For now, we'll skip it in the fallback
        
        # Define parallel groups: discovery first, then analysis can run in parallel
        parallel_groups = []
        if subtasks:
            # First group: discovery tasks
            discovery_tasks = [st.subtask_id for st in subtasks if st.agent_id == "catalog_scout"]
            if discovery_tasks:
                parallel_groups.append(discovery_tasks)
            
            # Second group: analysis tasks (can run in parallel after discovery)
            analysis_tasks = [st.subtask_id for st in subtasks if st.agent_id in ["data_steward", "quality_guardian"]]
            if analysis_tasks:
                parallel_groups.append(analysis_tasks)
        
        # If no parallel groups identified, run sequentially
        if not parallel_groups:
            parallel_groups = [[st.subtask_id] for st in subtasks]
        
        return ExecutionPlan(
            subtasks=subtasks,
            estimated_duration=f"{len(subtasks) * 30}s",  # Rough estimate
            parallel_groups=parallel_groups
        )