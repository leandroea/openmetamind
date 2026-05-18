"""
Orchestrator for OpenMetaMind.

This module provides a LangGraph ReAct agent that routes user requests to agents
using the framework's prebuilt ReAct agent pattern.
Each agent is exposed as a standalone tool for LLM-based routing decisions.
"""

import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .registry import AgentRegistry
from ..config import get_settings
from ..utils import strip_think

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    LangGraph ReAct agent that routes user requests to specialized agents.
    
    Uses create_react_agent to handle reasoning and tool execution automatically.
    Each agent is exposed as a separate tool. Routing is entirely LLM-based
    through the ReAct pattern - no hardcoded routing decisions.
    """
    
    SYSTEM_PROMPT = """You are the Orchestrator for OpenMetaMind, an autonomous multi-agent system 
for OpenMetadata data governance.

You have access to specialized agents that you can call directly. Each agent has specific
capabilities described in its tool definition. Analyze the user's request and call the
most appropriate agent tool to fulfill their request.

## Important Rules
- Choose the right tool based on the agent's capabilities and the user's request
- Be concise in your responses
- If no tool matches the request, respond directly without calling any agent
- Do not make up entity names or FQNs - let the agent handle that
"""
    
    def __init__(self):
        """Initialize the Orchestrator ReAct agent."""
        settings = get_settings()
        self.llm = settings.create_llm_client(temperature=0.1, max_tokens=500)
        self.registry = AgentRegistry()
        
        # Create tools from all registered agents
        tools = self._create_agent_tools()
        
        # Create prebuilt ReAct agent with all agent tools
        self.agent = create_react_agent(self.llm, tools, debug=False)
    
    def _create_agent_tools(self) -> list:
        """Create LangChain Tool objects from registered agents."""
        from langchain_core.tools import Tool
        
        tools = []
        
        for agent in self.registry.list_agents():
            agent_id = agent.agent_id
            display_name = agent.display_name
            description = agent.description
            capabilities = agent.capabilities
            
            # Build capability descriptions for the tool
            cap_list = []
            for cap in capabilities:
                if isinstance(cap, dict):
                    cap_list.append(f"- {cap.get('name', 'unknown')}: {cap.get('description', '')}")
                else:
                    cap_list.append(f"- {getattr(cap, 'name', 'unknown')}: {getattr(cap, 'description', '')}")
            
            capabilities_text = "\n".join(cap_list) if cap_list else "General assistance"
            
            # Create a tool for this agent
            def make_agent_executor(agent_instance):
                def execute_agent(task: str) -> str:
                    """
                    Execute a task using the {display_name} agent.
                    
                    Args:
                        task: A clear description of what to do
                    """
                    try:
                        import asyncio
                        result = asyncio.run(agent_instance.execute(
                            task=task,
                            inputs={},
                            mcp_client=None
                        ))
                        response = str(result) if result else "Task completed with no output"
                        return strip_think(response)
                    except Exception as e:
                        logger.error(f"[{agent_instance.agent_id}] Execution failed: {e}")
                        return f"Error: {str(e)}"
                return execute_agent
            
            tool = Tool(
                name=agent_id,
                description=f"""**{display_name}**: {description}

Capabilities:
{capabilities_text}

Use this agent when the user asks about tasks matching these capabilities.""",
                func=make_agent_executor(agent)
            )
            tools.append(tool)
            logger.info(f"Created tool for agent: {agent_id}")
        
        return tools
    
    def run(self, user_request: str, history: list = None) -> dict:
        """
        Run the orchestrator on a user request.
        
        Args:
            user_request: The user's input
            history: Optional conversation history
            
        Returns:
            Dict with response_text and success status
        """
        try:
            # Run the ReAct agent
            result = self.agent.invoke({
                "messages": [HumanMessage(content=user_request)]
            })
            
            # Extract messages
            messages = result.get("messages", [])
            final_message = messages[-1] if messages else None
            
            if final_message:
                return {
                    "success": True,
                    "response_text": strip_think(final_message.content),
                }
            else:
                return {
                    "success": False,
                    "response_text": "I wasn't able to process that request. Could you please rephrase?",
                }
                
        except Exception as e:
            logger.error(f"[Orchestrator] Execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "response_text": f"I encountered an error: {str(e)}. Could you try rephrasing?",
            }