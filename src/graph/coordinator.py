"""
Coordinator node for the OpenMetaMind swarm.

The Coordinator is the user's single point of contact. It maintains conversation memory
and decides whether to answer directly, delegate to swarm, or ask clarifying questions.
"""

from typing import Literal, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import os

from ..models.state import SwarmState


class Coordinator:
    """
    The Coordinator node in the LangGraph workflow.
    
    Responsibilities:
    - Maintain conversation memory
    - Classify user intent
    - Decide whether to answer directly, delegate to swarm, or ask clarifying questions
    """

    def __init__(self):
        """Initialize the Coordinator with NVIDIA LLM."""
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
        
        # Intent classification prompt
        self.intent_prompt = ChatPromptTemplate.from_template(
            """You are the Coordinator for OpenMetaMind, an autonomous multi-agent swarm for OpenMetadata data governance.
            
            Analyze the user's query and classify their intent into one of these categories:
            
            1. "answer_directly": The user is asking a simple factual question that can be answered from 
               conversation history or general knowledge without needing the swarm.
               
            2. "delegate_lightweight": The user is asking a simple governance task that requires 
               only a single agent (e.g., "what is the schema of table X?").
               
            3. "delegate_full_swarm": The user is asking a complex governance task that requires 
               multiple agents working together (e.g., "audit the customers database and fix governance gaps").
               
            4. "clarify": The user's query is ambiguous or lacks necessary information to proceed.
            
            User query: {user_query}
            
            Conversation history (last 5 messages):
            {conversation_history}
            
            Respond with a JSON object containing:
            {{
                "intent": "answer_directly" | "delegate_lightweight" | "delegate_full_swarm" | "clarify",
                "reasoning": "brief explanation of your decision",
                "suggested_clarification": "if intent is clarify, what question to ask the user"
            }}
            """
        )
        
        # Direct answer prompt
        self.answer_prompt = ChatPromptTemplate.from_template(
            """You are the Coordinator for OpenMetaMind. Provide a helpful direct answer to the user's question
            based on the conversation history.
            
            User query: {user_query}
            
            Conversation history:
            {conversation_history}
            
            Provide a clear, concise answer. If you don't know the answer, say so and suggest how the swarm could help.
            """
        )
        
        # Clarification prompt
        self.clarify_prompt = ChatPromptTemplate.from_template(
            """You are the Coordinator for OpenMetaMind. The user's query needs clarification.
            
            User query: {user_query}
            
            Conversation history:
            {conversation_history}
            
            Ask a clear, specific question to gather the information needed to proceed.
            """
        )
        
        # Set up chains
        self.intent_chain = self.intent_prompt | self.llm | JsonOutputParser()
        self.answer_chain = self.answer_prompt | self.llm
        self.clarify_chain = self.clarify_prompt | self.llm

    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute the Coordinator node.
        
        Args:
            state: Current swarm state
            
        Returns:
            Dictionary with state updates
        """
        user_query = state.get("user_input", "")
        conversation_history = state.get("conversation_history", [])
        
        # Format conversation history for the prompt
        history_str = "\n".join([
            f"{'Human' if isinstance(msg, HumanMessage) else 'AI'}: {msg.content}"
            for msg in conversation_history[-5:]  # Last 5 messages
        ])
        
        # Classify intent
        try:
            intent_result = self.intent_chain.invoke({
                "user_query": user_query,
                "conversation_history": history_str
            })
            
            intent = intent_result.get("intent", "clarify")
            reasoning = intent_result.get("reasoning", "")
            suggested_clarification = intent_result.get("suggested_clarification", "")
            
        except Exception as e:
            # Fallback to clarification if intent classification fails
            intent = "clarify"
            reasoning = f"Intent classification failed: {str(e)}"
            suggested_clarification = "Could you please clarify what you'd like me to help you with?"
        
        # Prepare state updates
        updates = {
            "conversation_history": conversation_history + [HumanMessage(content=user_query)]
        }
        
        if intent == "answer_directly":
            # Generate direct answer
            try:
                answer = self.answer_chain.invoke({
                    "user_query": user_query,
                    "conversation_history": history_str
                })
                updates["coordinator_response"] = answer.content if hasattr(answer, 'content') else str(answer)
            except Exception as e:
                updates["coordinator_response"] = f"I apologize, but I encountered an error while trying to answer your question: {str(e)}"
            
            # Route to END (handled by returning special value in LangGraph)
            updates["next"] = "end"
            
        elif intent == "clarify":
            # Generate clarification question
            try:
                clarification = self.clarify_chain.invoke({
                    "user_query": user_query,
                    "conversation_history": history_str
                })
                updates["coordinator_response"] = clarification.content if hasattr(clarification, 'content') else str(clarification)
            except Exception as e:
                updates["coordinator_response"] = suggested_clarification or f"I'm not sure I understand. Could you please clarify what you'd like me to help you with?"
            
            updates["next"] = "end"
            
        else:  # delegate_lightweight or delegate_full_swarm
            updates["delegated_task"] = user_query
            updates["next"] = "planner"
            
            # Add reasoning to conversation for transparency
            updates["conversation_history"] = updates["conversation_history"] + [
                AIMessage(content=f"I understand you'd like to: {user_query}\n\nMy analysis: {reasoning}\n\nI'm delegating this to the swarm for processing.")
            ]
        
        return updates