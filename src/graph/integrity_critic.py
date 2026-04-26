"""
Integrity Critic node for the OpenMetaMind swarm.

Validates all findings, detects conflicts, assigns confidence, and decides routing.
"""

from typing import List, Dict, Any, Optional, Tuple
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import os
import logging

from ..models.state import SwarmState, AgentFinding, Conflict, CriticDecision, CriticReview, FindingAssessment, ActionType, ProposedAction

logger = logging.getLogger(__name__)


class IntegrityCritic:
    """
    The Integrity Critic node in the LangGraph workflow.
    
    Responsibilities:
    - Read ALL findings from blackboard
    - Group findings by target_entity
    - Use LLM to detect conflicts between findings
    - For each finding: assign validity_score 0.0-1.0
    - Check if mcp_tool_calls are present (sufficient evidence)
    - Make CriticDecision: 
        - AUTO_APPROVE (all findings >0.9, no conflicts)
        - ESCALATE_TO_HUMAN (any conflict or finding <0.7)
        - REJECT_AND_RETRY (all findings <0.5)
    - Write conflicts to blackboard if detected
    - Aggregate proposed_actions into approved_actions, escalated_actions
    - Write critic_review to state
    - Route based on decision
    """

    def __init__(self):
        """Initialize the Integrity Critic with MiniMax LLM."""
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
        
        # Critic analysis prompt - focused on conflict detection and validation
        self.analysis_prompt = ChatPromptTemplate.from_template(
            """You are the Integrity Critic for OpenMetaMind, responsible for validating agent findings
            and ensuring data quality and consistency.
            
            Findings to review (grouped by target entity):
            {findings_by_entity}
            
            Your task is to:
            1. Validate each finding for correctness and completeness
            2. Detect any conflicts between findings about the same entity
            3. Assign validity scores (0.0-1.0) to each finding based on:
               - Presence of mcp_tool_calls (evidence)
               - Internal consistency
               - Plausibility of claims
            4. Determine if conflicts exist between findings
            5. Make a final routing decision based on these rules:
               - AUTO_APPROVE: All findings have validity_score > 0.9 AND no conflicts detected
               - ESCALATE_TO_HUMAN: Any conflict detected OR any finding has validity_score < 0.7
               - REJECT_AND_RETRY: All findings have validity_score < 0.5
            
            Respond with a JSON object containing:
            {{
                "findings_reviewed": <integer>,
                "conflicts_detected": <integer>,
                "finding_assessments": [
                    {{
                        "finding_id": "<finding_id>",
                        "validity_score": <float>,
                        "is_consistent_with_others": <boolean>,
                        "has_sufficient_evidence": <boolean>,
                        "mcp_calls_verified": <boolean>
                    }}
                ],
                "conflicts": [
                    {{
                        "finding_ids": ["<id1>", "<id2>"],
                        "agents_involved": ["<agent1>", "<agent2>"],
                        "description": "<description of conflict>",
                        "severity": "warning" | "critical"
                    }}
                ],
                "decision": "AUTO_APPROVE" | "ESCALATE_TO_HUMAN" | "REJECT_AND_RETRY",
                "reasoning": "<explanation of your decision>",
                "approved_actions": [<list of approved action dicts>],
                "rejected_actions": [<list of rejected action dicts>],
                "escalated_actions": [<list of escalated action dicts>]
            }}
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
        logger.info(f"Integrity Critic: Called with {len(state.get('findings', []))} findings")
        
        # Debug logging for received findings
        logger.info(f"[Critic] Received {len(state.get('findings', []))} findings")
        for i, f in enumerate(state.get('findings', [])):
            f_obj = AgentFinding(**f) if isinstance(f, dict) else f
            actions = getattr(f_obj, "proposed_actions", [])
            logger.info(f"[Critic] Finding {i} from {f_obj.agent_id}: confidence={f_obj.confidence}, actions_count={len(actions)}")
            for j, action in enumerate(actions):
                logger.info(f"[Critic]   Action {j}: type={action.action_type}, target={action.target_entity}")
        
        blackboard = state.get("blackboard", {})
        findings_raw = state.get("findings", [])  # Findings accumulated at top level via operator.add
        
        # Convert raw findings to AgentFinding objects if needed
        findings: List[AgentFinding] = []
        for f in findings_raw:
            if isinstance(f, dict):
                findings.append(AgentFinding(**f))
            else:
                findings.append(f)  # Already an AgentFinding object
        
        if not findings:
            # No findings to review
            critic_review = CriticReview(
                findings_reviewed=0,
                conflicts_detected=0,
                conflicts_resolved=0,
                conflicts_escalated=0,
                decision=CriticDecision.ESCALATE_TO_HUMAN,
                reasoning="No findings to review",
                approved_actions=[],
                rejected_actions=[],
                escalated_actions=[]
            )
            
            return {
                "critic_review": critic_review.model_dump(),
                "next": "human_gate"
            }
        
        # Group findings by target_entity for conflict detection
        findings_by_entity: Dict[str, List[AgentFinding]] = {}
        for finding in findings:
            # Skip zero-confidence findings with no proposed actions
            if finding.confidence == 0.0 and len(finding.proposed_actions) == 0:
                logger.warning(f"Finding from {finding.agent_id} has zero confidence and no actions — skipping")
                continue
            
            entity = finding.target_entity or "unknown"
            if entity not in findings_by_entity:
                findings_by_entity[entity] = []
            findings_by_entity[entity].append(finding)
        
        # If no actionable findings, return early with AUTO_APPROVE
        if not findings_by_entity:
            logger.info("No actionable findings to review — returning AUTO_APPROVE")
            critic_review = CriticReview(
                findings_reviewed=0,
                conflicts_detected=0,
                decision=CriticDecision.AUTO_APPROVE,
                reasoning="No actionable findings to review",
                approved_actions=[],
                rejected_actions=[],
                escalated_actions=[],
                conflicts=[]
            )
            return {
                "critic_review": critic_review.model_dump(),
                "next": "action_executor"
            }
        
        # Format findings for the prompt
        findings_str = ""
        for entity, entity_findings in findings_by_entity.items():
            findings_str += f"Entity: {entity}\n"
            for finding in entity_findings:
                findings_str += f"  - Finding ID: {finding.finding_id}\n"
                findings_str += f"    Agent: {finding.agent_id}\n"
                findings_str += f"    Summary: {finding.summary}\n"
                findings_str += f"    Confidence: {finding.confidence}\n"
                findings_str += f"    MCP Tool Calls: {len(finding.mcp_tool_calls)}\n"
                findings_str += f"    Details: {finding.details}\n\n"
        
        # Analyze findings with LLM
        try:
            critic_result = self.analysis_chain.invoke({
                "findings_by_entity": findings_str
            })
            
            # Process the LLM result
            finding_assessments = []
            for fa_dict in critic_result.get("finding_assessments", []):
                finding_assessments.append(FindingAssessment(**fa_dict))
            
            conflicts = []
            for conflict_dict in critic_result.get("conflicts", []):
                conflicts.append(Conflict(**conflict_dict))
            
            critic_review = CriticReview(
                findings_reviewed=critic_result.get("findings_reviewed", len(findings)),
                conflicts_detected=len(conflicts),
                conflicts_resolved=0,  # Would be updated if we auto-resolve
                conflicts_escalated=len([c for c in conflicts if c.severity == "critical"]),
                decision=CriticDecision(critic_result.get("decision", "escalate_to_human")),
                reasoning=critic_result.get("reasoning", "Critic analysis completed"),
                approved_actions=[ProposedAction(**a) for a in critic_result.get("approved_actions", [])],
                rejected_actions=[ProposedAction(**a) for a in critic_result.get("rejected_actions", [])],
                escalated_actions=[ProposedAction(**a) for a in critic_result.get("escalated_actions", [])]
            )
            
            # Debug: log decisions for each action
            for a in critic_result.get("approved_actions", []):
                action = ProposedAction(**a)
                logger.info(f"[Critic] Decision for {action.action_type} on {action.target_entity}: APPROVED")
            for a in critic_result.get("rejected_actions", []):
                action = ProposedAction(**a)
                logger.info(f"[Critic] Decision for {action.action_type} on {action.target_entity}: REJECTED")
            for a in critic_result.get("escalated_actions", []):
                action = ProposedAction(**a)
                logger.info(f"[Critic] Decision for {action.action_type} on {action.target_entity}: ESCALATED")
            
        except Exception as e:
            # Fallback critic decision based on simple heuristics
            finding_assessments = []
            conflicts = []
            
            for finding in findings:
                # Simple validity score based on confidence and MCP calls
                has_evidence = len(finding.mcp_tool_calls) > 0
                validity_score = min(finding.confidence + (0.1 if has_evidence else 0.0), 1.0)
                
                finding_assessments.append(FindingAssessment(
                    finding_id=finding.finding_id,
                    validity_score=validity_score,
                    is_consistent_with_others=True,  # Simplified - would check for conflicts
                    has_sufficient_evidence=has_evidence,
                    mcp_calls_verified=has_evidence
                ))
            
            # Simple conflict detection: findings with different summaries for same entity
            for entity, entity_findings in findings_by_entity.items():
                if len(entity_findings) > 1:
                    # Check if summaries are significantly different
                    summaries = [f.summary.lower() for f in entity_findings]
                    if len(set(summaries)) > 1:  # Different summaries
                        # Create a conflict between the first two findings
                        conflicts.append(Conflict(
                            finding_ids=[entity_findings[0].finding_id, entity_findings[1].finding_id],
                            agents_involved=[entity_findings[0].agent_id, entity_findings[1].agent_id],
                            description=f"Conflicting summaries for entity {entity}: '{entity_findings[0].summary}' vs '{entity_findings[1].summary}'",
                            severity="warning"
                        ))
            
            # Determine decision based on simple rules
            validity_scores = [fa.validity_score for fa in finding_assessments]
            has_conflicts = len(conflicts) > 0
            
            # Special case: discovery-only findings (no proposed_actions) should auto-approve
            all_discovery = all(len(f.proposed_actions) == 0 for f in findings)
            
            if all_discovery and all(score >= 0.8 for score in validity_scores) and not has_conflicts:
                decision = CriticDecision.AUTO_APPROVE
            elif all(score >= 0.9 for score in validity_scores) and not has_conflicts:
                decision = CriticDecision.AUTO_APPROVE
            elif any(score < 0.7 for score in validity_scores) or has_conflicts:
                decision = CriticDecision.ESCALATE_TO_HUMAN
            else:
                decision = CriticDecision.REJECT_AND_RETRY
            
            critic_review = CriticReview(
                findings_reviewed=len(findings),
                conflicts_detected=len(conflicts),
                conflicts_resolved=0,
                conflicts_escalated=len([c for c in conflicts if c.severity == "critical"]),
                decision=decision,
                reasoning=f"Fallback critic analysis: {len(findings)} findings reviewed, {len(conflicts)} conflicts detected",
                approved_actions=[],
                rejected_actions=[],
                escalated_actions=[]
            )
            
            # For fallback, we still need to collect all proposed actions as escalated (since we can't trust them)
            all_proposed_actions = []
            for finding in findings:
                all_proposed_actions.extend(finding.proposed_actions)
                for action in finding.proposed_actions:
                    logger.info(f"[Critic] Fallback ESCALATED: {action.action_type} on {action.target_entity}")
            critic_review.escalated_actions = all_proposed_actions
        
        # Add any new conflicts to the blackboard
        updated_conflicts = list(blackboard.get("conflicts", []))
        updated_conflicts.extend(conflicts)
        
        # Determine next step based on decision
        decision = critic_review.decision
        if decision == CriticDecision.AUTO_APPROVE:
            next_step = "action_executor"
        elif decision == CriticDecision.REJECT_AND_RETRY:
            next_step = "planner"  # Go back to planner to regenerate plan
        else:  # ESCALATE_TO_HUMAN
            next_step = "human_gate"
        
        # Prepare state updates
        # Note: findings and agent_statuses are at top level with operator.add
        updates = {
            "critic_review": critic_review.model_dump(),
            "blackboard": {
                # Only keep conflicts in blackboard - other fields are at top level
                "conflicts": updated_conflicts,  # Add new conflicts
                "execution_phase": "reviewing"
            },
            "next": next_step
        }
        
        # If we have approved actions, add them to state for action executor
        if critic_review.approved_actions:
            updates["approved_actions"] = [action.model_dump() for action in critic_review.approved_actions]
        
        # Always expose pending human actions at top level for Streamlit UI
        if critic_review.escalated_actions:
            updates["pending_human_actions"] = [action.model_dump() for action in critic_review.escalated_actions]
        
        if critic_review.approved_actions:
            updates["pending_human_actions"] = [action.model_dump() for action in critic_review.approved_actions]
        
        logger.info(f"Integrity Critic: Decision = {decision.value}, next = {next_step}, approved_actions = {len(critic_review.approved_actions)}, escalated_actions = {len(critic_review.escalated_actions)}")
        
        return updates