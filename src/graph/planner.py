"""
Planner node for the OpenMetaMind swarm.

The Planner decomposes tasks into subtasks and selects appropriate agents.
It generates an ExecutionPlan for sequential execution via the Supervisor pattern.
"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import os
import logging
import re

from ..models.plan import Subtask, ExecutionPlan
from ..models.state import SwarmState
from ..agents.registry import AgentRegistry
from ..utils import strip_think

logger = logging.getLogger(__name__)


class MiniMaxJsonOutputParser(JsonOutputParser):
    """
    Custom JSON parser that handles responses from MiniMax models.
    
    MiniMax models sometimes include thinking tags like <think> ... 
    and special tokens like <|im_end|> in their responses. This parser
    extracts the JSON portion from such responses.
    """
    
    def parse_result(self, result, *, partial: bool = False):
        """Extract clean JSON from LLM response and parse it.
        
        Handles the LangChain output parser format where result is a list
        of ChatGeneration objects: [ChatGeneration(message=AIMessage(...))]
        """
        # Unwrap from LangChain's list format if needed
        raw_result = result
        if isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            if hasattr(first_item, 'message'):
                # This is a ChatGeneration object
                message = first_item.message
                if hasattr(message, 'content'):
                    raw_text = message.content
                elif hasattr(message, 'text'):
                    raw_text = message.text
                else:
                    raw_text = str(message)
            elif hasattr(first_item, 'text'):
                raw_text = first_item.text
            else:
                raw_text = str(first_item)
        elif hasattr(result, 'content'):
            raw_text = result.content
        elif hasattr(result, 'text'):
            raw_text = result.text
        else:
            raw_text = str(result)
        
        # Validate we got a string
        if not isinstance(raw_text, str):
            raise ValueError(f"Expected string from LLM, got {type(raw_text)}")
        
        text = raw_text
        logger.info(f"Planner: Raw LLM response length: {len(text)}")
        logger.info(f"Planner: Raw LLM text preview: {text[:200]}...")
        
        # Use strip_think to remove all chain-of-thought blocks
        text = strip_think(text)
        
        # Validate text is not empty after stripping
        if not text or text.isspace():
            raise ValueError(f"LLM returned empty content after stripping. Raw: {repr(raw_text[:200])}")
        
        # Remove remaining special tokens
        text = re.sub(r'<\|im_end\|>', '', text)
        text = re.sub(r'<\|[^|]+\|>', '', text)
        
        # Validate again after token removal
        if not text or text.isspace():
            raise ValueError(f"Text became empty after token removal. Raw: {repr(raw_text[:200])}")
        
        # Look for JSON object or array
        json_start = text.find('{')
        if json_start == -1:
            json_start = text.find('[')
        
        if json_start == -1:
            # No JSON found at all - raise error with full text
            raise ValueError(f"No JSON found in response. Text: {repr(text[:500])}")
        
        if json_start != -1:
            text = text[json_start:]
            
            # Find the end by counting braces/brackets
            if text.startswith('{'):
                depth = 0
                for i, c in enumerate(text):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            text = text[:i+1]
                            break
            elif text.startswith('['):
                depth = 0
                for i, c in enumerate(text):
                    if c == '[':
                        depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            text = text[:i+1]
                            break
        
        # Debug: log the full extracted text with ordinals for each char
        logger.info(f"Planner: Extracted JSON text length: {len(text)}")
        logger.info(f"Planner: Full text repr: {repr(text[:500])}")
        logger.info(f"Planner: Extracted JSON candidate: '{text[:300]}...'")
        
        # Try to parse the cleaned JSON
        import json
        try:
            parsed = json.loads(text)
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Planner: First JSON parse failed: {e}")
            
            # Try to fix common issues with LLM JSON output
            import ast
            try:
                # Use ast.literal_eval as fallback for Python-style dicts
                parsed = ast.literal_eval(text)
                if isinstance(parsed, dict):
                    return parsed
                elif isinstance(parsed, list):
                    return {"subtasks": parsed, "estimated_duration": "unknown"}
            except Exception as e2:
                logger.warning(f"Planner: ast.literal_eval failed: {e2}")
            
            # Last resort: try manual fixes
            text_fixed = text
            text_fixed = re.sub(r"'([^']+)':", r'"\1":', text_fixed)  # Single-quoted keys
            text_fixed = re.sub(r":\s*'([^']*)'", r': "\1"', text_fixed)  # Single-quoted values
            text_fixed = re.sub(r': None', ': null', text_fixed)
            text_fixed = re.sub(r': True', ': true', text_fixed)
            text_fixed = re.sub(r': False', ': false', text_fixed)
            # Handle literal \\n (backslash-n) sequences - replace with actual newlines
            text_fixed = text_fixed.replace(r'\n', '\n')
            text_fixed = text_fixed.strip()
            
            logger.info(f"Planner: Fixed JSON attempt: '{text_fixed[:300]}...'")
            try:
                parsed = json.loads(text_fixed)
                return parsed
            except json.JSONDecodeError as e3:
                logger.error(f"Planner: All JSON parsing attempts failed. Final text: '{text_fixed[:500]}'")
                # DEV MODE: Raise error instead of silent fallback to aid debugging
                raise RuntimeError(f"Planner failed to produce valid JSON. Parse error: {e3}. Text: {text_fixed[:300]}...")
        
    def _extract_text_from_result(self, result) -> str:
        """Extract text from LLM result object.
        
        Handles various LangChain result formats:
        - AIMessage: result.content
        - ChatResult: result.generations[0][0].text
        - Raw string: result
        """
        if hasattr(result, 'content'):
            return result.content
        if hasattr(result, 'text'):
            return result.text
        if hasattr(result, 'generations') and result.generations:
            first_gen = result.generations[0][0]
            if hasattr(first_gen, 'text'):
                return first_gen.text
        return str(result)


class Planner:
    """
    The Planner node in the LangGraph workflow.
    
    Responsibilities:
    - Task decomposition and agent selection
    - Generate ExecutionPlan for sequential execution via Supervisor pattern
    - Query Agent Registry for agent capabilities
    """

    def __init__(self):
        """Initialize the Planner with MiniMax LLM."""
        # Initialize ChatOpenAI with MiniMax endpoint
        minimax_api_key = os.getenv("MINIMAX_API_KEY")
        if not minimax_api_key:
            raise ValueError("MINIMAX_API_KEY must be set in environment variables")
        
        self.llm = ChatOpenAI(
            base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
            api_key=minimax_api_key,
            model=os.getenv("LLM_MODEL", "minimax-m2.7"),
            temperature=0.1,
            max_tokens=1000
        )
        
        # Task decomposition prompt
        self.decomposition_prompt = ChatPromptTemplate.from_template(
            """Decompose this task into subtasks. Output ONLY valid JSON in this exact format:

{subtask_format}

No markdown, no explanation, no thinking tags.

User request: {user_request}

Available agents:
{agent_capabilities}

IMPORTANT: When the user request mentions a specific table or entity (e.g., "the big_data_table_with_nested_columns table" or "sample_data.ecommerce_db.shopify.big_data_table_with_nested_columns"), you MUST:
1. Include the table's fully qualified name (FQN) in the required_inputs of the subtask that will use it
2. Use the format: "table_fqn: <full_fqn>" in required_inputs
3. The discovering agent (catalog_scout) should produce output that the next agent can use

Example:
- Task: "Document the big_data_table_with_nested_columns table"
- Subtask: {{"subtask_id": "discover_table", "agent_id": "catalog_scout", "task_description": "Find the big_data_table_with_nested_columns table", "required_inputs": [], "produces_output": "table_fqn"}}
- Then documentation_agent with "required_inputs": ["table_fqn"]

Examples:
- Task: "Find all tables missing descriptions" -> catalog_scout first, then documentation_agent
- Task: "Check data quality for customer_orders" -> catalog_scout first to find the table, then quality_guardian
- Task: "Profile the big_data_table_with_nested_columns table" -> catalog_scout to find it, then quality_guardian with table_fqn
"""
        )
        
        # Set up chain with custom parser that handles MiniMax thinking tags
        self.decomposition_chain = self.decomposition_prompt | self.llm | MiniMaxJsonOutputParser()

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
        
        # Format agent capabilities for the prompt - just ID, name, one-line description
        agent_capabilities_str = ""
        for agent in agents:
            agent_capabilities_str += f"- {agent.agent_id}: {agent.description}\n"
        
        logger.info(f"Planner: Invoking decomposition chain for task: {delegated_task[:50]}...")
        
        # Decompose task into subtasks
        subtask_format = '{"subtasks": [{"subtask_id": "...", "agent_id": "...", "task_description": "...", "required_inputs": [], "produces_output": "...", "dependencies": [], "max_retries": 2, "timeout_seconds": 60}]}'
        try:
            plan_result = self.decomposition_chain.invoke({
                "user_request": delegated_task,
                "agent_capabilities": agent_capabilities_str,
                "subtask_format": subtask_format
            })
            
            logger.info(f"Planner: Decomposition successful, got {len(plan_result.get('subtasks', []))} subtasks")
            
            # Convert to ExecutionPlan object
            subtasks = [Subtask(**subtask_dict) for subtask_dict in plan_result.get("subtasks", [])]
            # parallel_groups removed - Supervisor pattern uses sequential execution via dependencies
            execution_plan = ExecutionPlan(
                subtasks=subtasks,
                estimated_duration=plan_result.get("estimated_duration", "unknown")
            )
            
        except Exception as e:
            logger.error(f"Planner: Decomposition failed: {str(e)}", exc_info=True)
            # Fallback to hardcoded decomposition if LLM fails
            logger.info("Planner: Using fallback plan")
            execution_plan = self._create_fallback_plan(delegated_task, agents)
        
        # Prepare state updates
        updates = {
            "execution_plan": execution_plan.model_dump() if hasattr(execution_plan, 'model_dump') else execution_plan,
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
        
        # Supervisor pattern: agents execute sequentially
        # For fallback, we just ensure dependencies are set based on agent order
        # Note: parallel_groups variable is unused but kept for reference during transition
        
        return ExecutionPlan(
            subtasks=subtasks,
            estimated_duration=f"{len(subtasks) * 30}s"  # Rough estimate
        )