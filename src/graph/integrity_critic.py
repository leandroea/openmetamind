"""
Integrity Critic node for the OpenMetaMind swarm.

Validates all findings, detects conflicts, assigns confidence, and decides routing.
"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import os

from ..models.state import SwarmState, AgentFinding, Conflict, CriticDecision
from ..models.plan import ExecutionPlan


class IntegrityCritic:
    """
    The Integrity Critic node in the LangGraph workflow.
    
    Responsibilities:
    - Validate all findings from agents
    - Detect conflicts between findings
    - Assign final confidence scores
    - Decide routing: auto-approve, human gate, or reject/retry
    """

    def __init__(self):
        """Initialize the Integrity Critic with NVIDIA LLM."""
        # Initialize ChatOpenAI with NVIDIA endpoint
        nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        if not nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY must be set in environment variables")
        
        self.llm = ChatOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_api_key,
            model="minimax/minimax-m2.5",
            temperature=0.1,
            max_tokens=1000
        )
        
        # Critic analysis prompt
        self.analysis_prompt = ChatPromptTemplate.from_template(
            """You are the Integrity Critic for OpenMetaMind, responsible for validating agent findings
            and ensuring data quality and consistency.
            
            Findings to review:
            {findings}
            
            Execution plan that generated these findings:
            {execution_plan}
            
            Your task is to:
            1. Validate each finding for correctness and completeness
            2. Detect any conflicts between findings
            3. Assign validity scores (0.0-1.0) to each finding
            4. Determine if conflicts can be resolved automatically or need human intervention
            5. Make a final routing decision
            
            Respond with a JSON object containing:
            {{
                "findings_reviewed": <integer>,
                "conflicts_detected": <integer>,
                "conflicts_resolved": <integer>,
                "conflicts_escalated": <integer>,
                "finding_assessments": [
                    {{
                        "finding_id": "<finding_id>",
                        "validity_score": <float>,
                        "is_consistent_with_others": <boolean>,
                        "has_sufficient_evidence": <boolean>,
                        "mcp_calls_verified": <boolean>
                    }}
                ],
                "decision": "AUTO_APPROVE" | "ESCALATE_TO_HUMAN" | "REJECT_AND_RETRY",
                "reasoning": "<explanation of your decision>",
                "approved_actions": [<list of approved action dicts>],
                "rejected_actions": [<list of rejected action dicts>],
                "escalated_actions": [<list of escalated action dicts>]
            }}
            
            Guidelines:
            - AUTO_APPROVE: High confidence, no conflicts, sufficient evidence
            - ESCALATE_TO_HUMAN: Conflicts that need human judgment, low confidence, or insufficient evidence
            - REJECT_AND_RETRY: Findings are fundamentally flawed, need to redo with different approach
            """
        )
        
        # Set up chain
        self.analysis_chain = self.analysis_prompt | self.llm | JsonOutputParser()

    def __call__(self, state: SwarmState) -> Dict[str, Any]:
        """
        Execute the Integrity Critic node.
        
        Args:
            state: Current swarm state containing blackboard with findings
            
        Returns:
            Dictionary with state updates including critic review and routing decision
        """
        blackboard = state.get("blackboard", {})
        findings = blackboard.get("findings", [])
        execution_plan = state.get("execution_plan", {})
        
        if not findings:
            # No findings to review
            return {
                "critic_review": {
                    "findings_reviewed": 0,
                    "conflicts_detected": 0,
                    "conflicts_resolved": 0,
                    "conflicts_escalated": 0,
                    "decision": "ESCALATE_TO_HUMAN",
                    "reasoning": "No findings to review",
                    "approved_actions": [],
                    "rejected_actions": [],
                    "escalated_actions": []
                },
                "next": "human_gate"  # Go to human gate since no findings
            }
        
        # Format findings for the prompt
        findings_str = ""
        for finding in findings:
            if isinstance(finding, dict):
                finding_str += f"- Finding ID: {finding.get('finding_id', 'unknown')}\n"
                finding_str += f"  Agent: {finding.get('agent_id', 'unknown')}\n"
                finding_str += f"  Summary: {finding.get('summary', 'no summary')}\n"
                finding_str += f"  Confidence: {finding.get('confidence', 0.0)}\n"
                finding_str += f"  Details: {finding.get('details', {})}\n\n"
            else:
                # Assuming it's an AgentFinding object
                finding_str += f"- Finding ID: {getattr(finding, 'finding_id', 'unknown')}\n"
                finding_str += f"  Agent: {getattr(finding, 'agent_id', 'unknown')}\n"
                finding_str += f"  Summary: {getattr(finding, 'summary', 'no summary')}\n"
                finding_str += f"  Confidence: {getattr(finding, 'confidence', 0.0)}\n"
                finding_str += f"  Details: {getattr(finding, 'details', {})}\n\n"
        
        # Format execution plan for the prompt
        plan_str = ""
        if isinstance(execution_plan, dict):
            plan_str = f"Subtasks: {len(execution_plan.get('subtasks', []))}\n"
            plan_str += f"Parallel groups: {execution_plan.get('parallel_groups', [])}\n"
        else:
            plan_str = f"Execution plan object: {type(execution_plan)}"
        
        # Analyze findings
        try:
            critic_result = self.analysis_chain.invoke({
                "findings": findings_str,
                "execution_plan": plan_str
            })
            
            # Convert to expected format
            critic_review = {
                "findings_reviewed": critic_result.get("findings_reviewed", len(findings)),
                "conflicts_detected": critic_result.get("conflicts_detected", 0),
                "conflicts_resolved": critic_result.get("conflicts_resolved", 0),
                "conflicts_escalated": critic_result.get("conflicts_escalated", 0),
                "decision": critic_result.get("decision", "ESCALATE_TO_HUMAN"),
                "reasoning": critic_result.get("reasoning", "Critic analysis completed"),
                "approved_actions": critic_result.get("approved_actions", []),
                "rejected_actions": critic_result.get("rejected_actions", []),
                "escalated_actions": critic_result.get("escalated_actions", [])
            }
            
        except Exception as e:
            # Fallback critic decision
            critic_review = {
                "findings_reviewed": len(findings),
                "conflicts_detected": 0,
                "conflicts_resolved": 0,
                "conflicts_escalated": 0,
                "decision": "ESCALATE_TO_HUMAN",
                "reasoning": f"Critic analysis failed: {str(e)}. Escalating to human for safety.",
                "approved_actions": [],
                "rejected_actions": [],
                "escalated_actions": []
            }
        
        # Determine next step based on decision
        decision = critic_review.get("decision", "ESCALATE_TO_HUMAN")
        if decision == "AUTO_APPROVE":
            next_step = "action_executor"
        elif decision == "REJECT_AND_RETRY":
            next_step = "planner"  # Go back to planner to regenerate plan
        else:  # ESCALATE_TO_HUMAN or default
            next_step = "human_gate"
        
        # Prepare state updates
        updates = {
            "critic_review": critic_review,
            "next": next_step
        }
        
        # If we have approved actions, add them to state for action executor
        if critic_review.get("approved_actions"):
            updates["approved_actions"] = critic_review["approved_actions"]
        
        return updates