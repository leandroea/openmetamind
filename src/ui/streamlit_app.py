"""
Streamlit UI for OpenMetaMind hackathon demo.

A visually stunning dashboard for the autonomous multi-agent swarm.
"""

import streamlit as st
import requests
import json
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
load_dotenv()

# Initialize logging
from src.config import setup_logging
setup_logging()

from src.utils import strip_think
import logging
logger = logging.getLogger(__name__)

import websocket
import threading

# Page configuration
st.set_page_config(
    page_title="OpenMetaMind",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for stunning visuals
st.markdown("""
<style>
    /* Main theme colors */
    :root {
        --primary: #6366f1;
        --secondary: #8b5cf6;
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
        --bg-dark: #0f172a;
        --bg-card: #1e293b;
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid #334155;
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
        color: #f1f5f9;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Agent card */
    .agent-card {
        background: #1e293b;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        border-left: 4px solid #6366f1;
    }
    
    /* Finding card */
    .finding-card {
        background: #1e293b;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
        border: 1px solid #334155;
    }
    
    /* Confidence badges */
    .badge-high { background: #10b981; color: white; padding: 4px 12px; border-radius: 20px; }
    .badge-medium { background: #f59e0b; color: white; padding: 4px 12px; border-radius: 20px; }
    .badge-low { background: #ef4444; color: white; padding: 4px 12px; border-radius: 20px; }
    
    /* Conflict box */
    .conflict-box {
        background: #7f1d1d;
        border: 2px solid #ef4444;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
    }
    
    /* Status indicators */
    .status-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 8px;
    }
    .status-running { background: #f59e0b; animation: pulse 1.5s infinite; }
    .status-completed { background: #10b981; }
    .status-failed { background: #ef4444; }
    .status-idle { background: #64748b; }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
    
    /* Chat messages */
    .user-message {
        background: #6366f1;
        color: white;
        border-radius: 16px 16px 4px 16px;
        padding: 12px 16px;
        margin: 8px 0;
    }
    
    .assistant-message {
        background: #1e293b;
        border-radius: 16px 16px 16px 4px;
        padding: 12px 16px;
        margin: 8px 0;
        border: 1px solid #334155;
    }
</style>
""", unsafe_allow_html=True)


# Direct import for swarm runner
from src.ui.swarm_runner import get_swarm_runner

# API Configuration - no longer needed for swarm calls
# Keeping for backward compatibility if needed
# API_BASE_URL = "http://localhost:8000"


def init_session_state():
    """Initialize session state variables."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "blackboard" not in st.session_state:
        st.session_state.blackboard = {"findings": [], "conflicts": [], "agent_statuses": {}}
    if "pending_approvals" not in st.session_state:
        st.session_state.pending_approvals = []
    if "pending_human_actions" not in st.session_state:
        st.session_state.pending_human_actions = []
    if "last_swarm_state" not in st.session_state:
        st.session_state.last_swarm_state = None
    if "human_actions_processed" not in st.session_state:
        st.session_state.human_actions_processed = False
    if "execution_plan" not in st.session_state:
        st.session_state.execution_plan = None
    if "is_running" not in st.session_state:
        st.session_state.is_running = False
    if "mcp_status" not in st.session_state:
        st.session_state.mcp_status = "unknown"


def get_agents() -> List[Dict[str, Any]]:
    """Fetch registered agents from the agent registry."""
    from src.agents.registry import AgentRegistry
    registry = AgentRegistry()
    agents = registry.list_agents()
    
    return [
        {
            "agent_id": agent.agent_id,
            "display_name": agent.display_name,
            "description": agent.description,
            "avatar_emoji": agent.avatar_emoji,
            "capabilities": [
                {
                    "name": cap.name,
                    "description": cap.description,
                    "input_schema": cap.input_schema,
                    "output_schema": cap.output_schema
                }
                for cap in agent.capabilities
            ]
        }
        for agent in agents
    ]


def get_swarm_status(session_id: str) -> Optional[Dict[str, Any]]:
    """Get swarm status from checkpointer - not used in direct mode."""
    # In direct mode, we don't maintain separate session state via API
    return None


def run_swarm(query: str, user_id: str = "demo_user") -> Optional[Dict[str, Any]]:
    """Run a swarm query directly via SwarmRunner."""
    try:
        runner = get_swarm_runner()
        return runner.run(query, user_id)
    except Exception as e:
        import traceback
        logger.error(f"COORDINATOR CRASH:\n{traceback.format_exc()}")
        st.error(f"Error running swarm: {e}")
        return None


def approve_actions(session_id: str, action_ids: List[str], decision: str) -> bool:
    """Approve or reject actions - not used in direct mode."""
    # In direct mode, actions are handled automatically by the swarm
    return True


def check_health() -> Dict[str, str]:
    """Check MCP and swarm health status directly."""
    try:
        from src.mcp.client import get_mcp_client
        client = get_mcp_client()
        # Just verify client can be created, not actually connect
        return {"status": "healthy", "mcp_connection": "configured"}
    except Exception as e:
        return {"status": "unhealthy", "mcp_connection": f"error: {str(e)}"}


def get_confidence_badge(confidence: float) -> str:
    """Get HTML for confidence badge."""
    if confidence >= 0.9:
        return '<span class="badge-high">HIGH</span>'
    elif confidence >= 0.7:
        return '<span class="badge-medium">MED</span>'
    else:
        return '<span class="badge-low">LOW</span>'


def get_status_dot(status: str) -> str:
    """Get HTML for status dot."""
    status_class = {
        "running": "status-running",
        "completed": "status-completed",
        "failed": "status-failed",
        "idle": "status-idle"
    }.get(status.lower(), "status-idle")
    return f'<span class="status-dot {status_class}"></span>'


def render_top_bar():
    """Render the top metrics bar."""
    st.markdown("### 🧠 OpenMetaMind Coordinator")
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    # Active Agents
    agents = get_agents()
    active_count = len(agents)
    with col1:
        st.metric(
            label="Active Agents",
            value=active_count,
            delta="Registered"
        )
    
    # Blackboard Items
    findings_count = len(st.session_state.blackboard.get("findings", []))
    with col2:
        st.metric(
            label="Blackboard Items",
            value=findings_count,
            delta="Findings"
        )
    
    # Pending Approvals
    pending_count = len(st.session_state.pending_approvals)
    with col3:
        st.metric(
            label="Pending Approvals",
            value=pending_count,
            delta="Actions" if pending_count > 0 else None
        )
    
    # MCP Status
    health = check_health()
    mcp_ok = health.get("mcp_connection") == "configured"
    with col4:
        st.metric(
            label="MCP Status",
            value="🟢 Connected" if mcp_ok else "🔴 Disconnected",
            delta=health.get("mcp_connection", "unknown")
        )


def render_sidebar():
    """Render the agent roster sidebar."""
    st.sidebar.title("🤖 Agent Roster")
    st.sidebar.markdown("---")
    
    agents = get_agents()
    agent_statuses = st.session_state.blackboard.get("agent_statuses", {})
    
    for agent in agents:
        status = agent_statuses.get(agent["agent_id"], "idle")
        status_html = get_status_dot(status)
        
        st.sidebar.markdown(f"""
        <div class="agent-card">
            <div style="display: flex; align-items: center;">
                <span style="font-size: 1.5rem; margin-right: 8px;">{agent.get('avatar_emoji', '🤖')}</span>
                <div>
                    <strong>{agent.get('display_name', agent['agent_id'])}</strong>
                    <br>
                    <small style="color: #94a3b8;">{status_html}{status.upper()}</small>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Show capabilities in expander
        with st.sidebar.expander(f"📋 Capabilities"):
            for cap in agent.get("capabilities", []):
                st.markdown(f"**{cap['name']}**: {cap['description']}")
    
    st.sidebar.markdown("---")
    st.sidebar.caption("OpenMetaMind v0.1.0")


def render_chat_tab():
    """Render the chat interface tab."""
    st.subheader("💬 Chat with Coordinator")
    
    # Display chat messages
    chat_container = st.container(border=True)
    with chat_container:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant"):
                    st.markdown(msg["content"])
    
    # Chat input
    if prompt := st.chat_input("What would you like me to help you with?"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()
    
    # Process user input and run swarm
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        user_input = st.session_state.messages[-1]["content"]
        
        # Reset approval state for new swarm run
        st.session_state.human_actions_processed = False
        st.session_state.pending_human_actions = []
        st.session_state.pending_approvals = []
        
        # Add assistant thinking message
        with st.chat_message("assistant"):
            with st.spinner("🧠 Analyzing your request..."):
                st.markdown("I'm processing your request with the swarm...")
        
        # Run the swarm
        result = run_swarm(user_input)
        
        if result:
            st.session_state.session_id = result.get("session_id")
            st.session_state.last_swarm_state = result.get("final_state")
            st.session_state.human_actions_processed = False
            
            # Update blackboard
            if "blackboard_summary" in result:
                summary = result["blackboard_summary"]
                st.session_state.blackboard = {
                    "findings": summary.get("findings", []),
                    "conflicts": summary.get("conflicts", []),
                    "agent_statuses": summary.get("agent_statuses", {})
                }
            
            # Update pending approvals and human actions from full state
            final_state = result.get("final_state", {})
            st.session_state.pending_approvals = result.get("approved_actions", [])
            st.session_state.pending_human_actions = result.get("pending_human_actions", final_state.get("pending_human_actions", []))
            
            # CRITICAL FIX: Extract escalated actions from critic_review if swarm_runner didn't populate them
            if not st.session_state.pending_human_actions and "critic_review" in final_state:
                critic_review = final_state["critic_review"]
                # critic_review may be a Pydantic model or a dict
                if hasattr(critic_review, "escalated_actions"):
                    st.session_state.pending_human_actions = critic_review.escalated_actions
                    st.session_state.pending_approvals = critic_review.approved_actions
                elif isinstance(critic_review, dict):
                    st.session_state.pending_human_actions = critic_review.get("escalated_actions", [])
                    st.session_state.pending_approvals = critic_review.get("approved_actions", [])
                logger.info(f"Extracted {len(st.session_state.pending_human_actions)} escalated actions from critic_review")
            
            # Add coordinator response
            response_text = result.get("coordinator_response", "The swarm has completed its analysis.")
            pending = st.session_state.pending_human_actions
            if pending:
                response_text += f"\n\n📋 **{len(pending)} actions pending human approval**"
            
            st.session_state.messages.append({"role": "assistant", "content": response_text})
        else:
            st.session_state.messages.append({
                "role": "assistant", 
                "content": "I apologize, but I couldn't process your request. Please ensure the backend is running and try again."
            })
        
        st.rerun()


def render_swarm_theater_tab():
    """Render the live blackboard feed tab."""
    st.subheader("🎭 Swarm Theater - Live Blackboard")
    
    # Create two columns: findings and conflicts
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 📊 Findings")
        findings_container = st.container(border=True, height=500)
        
        with findings_container:
            findings = st.session_state.blackboard.get("findings", [])
            
            if not findings:
                st.info("No findings yet. Run a query to see agent findings here.")
            else:
                for i, finding in enumerate(findings):
                    # Extract finding data
                    if isinstance(finding, dict):
                        agent_id = finding.get("agent_id", "unknown")
                        summary = strip_think(finding.get("summary", "No summary"))
                        confidence = finding.get("confidence", 0.0)
                        timestamp = finding.get("timestamp", "")
                        finding_type = finding.get("finding_type", "other")
                    else:
                        agent_id = getattr(finding, "agent_id", "unknown")
                        summary = strip_think(getattr(finding, "summary", "No summary"))
                        confidence = getattr(finding, "confidence", 0.0)
                        timestamp = getattr(finding, "timestamp", "")
                        finding_type = getattr(finding, "finding_type", "other")
                    
                    # Format timestamp
                    if timestamp:
                        try:
                            if isinstance(timestamp, datetime):
                                time_str = timestamp.strftime("%H:%M:%S")
                            elif isinstance(timestamp, str):
                                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                time_str = dt.strftime("%H:%M:%S")
                            else:
                                time_str = str(timestamp)[:8] if len(str(timestamp)) > 8 else str(timestamp)
                        except:
                            time_str = datetime.now().strftime("%H:%M:%S")
                    else:
                        time_str = datetime.now().strftime("%H:%M:%S")
                    
                    badge = get_confidence_badge(confidence)
                    
                    st.markdown(f"""
                    <div class="finding-card">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <div>
                                <strong>🤖 {agent_id}</strong>
                                <span style="margin-left: 8px; color: #64748b;">[{finding_type}]</span>
                                <br>
                                <span style="color: #cbd5e1;">{summary}</span>
                            </div>
                            <div style="text-align: right;">
                                {badge}
                                <br>
                                <small style="color: #64748b;">{time_str}</small>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("### ⚠️ Conflicts")
        conflicts_container = st.container(border=True, height=500)
        
        with conflicts_container:
            conflicts = st.session_state.blackboard.get("conflicts", [])
            
            if not conflicts:
                st.success("No conflicts detected ✓")
            else:
                for conflict in conflicts:
                    if isinstance(conflict, dict):
                        description = conflict.get("description", "Unknown conflict")
                        severity = conflict.get("severity", "warning")
                    else:
                        description = getattr(conflict, "description", "Unknown conflict")
                        severity = getattr(conflict, "severity", "warning")
                    
                    st.markdown(f"""
                    <div class="conflict-box">
                        <strong>⚠️ {severity.upper()}</strong>
                        <br>
                        {description}
                    </div>
                    """, unsafe_allow_html=True)


def render_execution_dag_tab():
    """Render the execution DAG visualization tab."""
    st.subheader("📈 Execution Plan DAG")
    
    plan = st.session_state.execution_plan
    
    if not plan:
        st.info("No execution plan yet. Run a query to see the plan DAG here.")
        
        # Show placeholder DAG
        st.markdown("""
        ```mermaid
        graph TD
            A[User Query] --> B[Coordinator]
            B --> C[Planner]
            C --> D[Dispatcher]
            D --> E1[Agent 1]
            D --> E2[Agent 2]
            D --> E3[Agent 3]
            E1 --> F[Integrity Critic]
            E2 --> F
            E3 --> F
            F --> G[Action Executor]
            F --> H[Human Gate]
        ```
        """)
    else:
        # Render actual DAG from plan
        st.json(plan)


def render_audit_tab():
    """Render the audit log tab."""
    st.subheader("📋 Audit Log - MCP Calls")
    
    st.info("MCP call audit trail will appear here after execution.")
    
    # Placeholder for audit data
    st.markdown("""
    | Timestamp | Agent | Tool | Status | Duration |
    |-----------|-------|------|--------|----------|
    | - | - | - | - | - |
    """)


def render_approval_gate():
    """
    Render the human approval panel when there are pending actions.
    
    Requirements:
    1. Check for pending_human_actions in session state
    2. Display action type, target entity, proposed change preview, confidence
    3. "Approve All" and "Reject All" buttons
    4. On Approve: call execute_pending_actions, show success/warning, clear actions
    5. On Reject: clear actions, show info message
    6. Prevent double-execution using human_actions_processed flag
    """
    # Check if we have pending human actions
    if "last_swarm_state" not in st.session_state:
        return
    
    pending = st.session_state.get("pending_human_actions", [])
    
    # If already processed, don't show the panel
    if st.session_state.get("human_actions_processed", False):
        return
    
    if not pending:
        return
    
    st.markdown("""
    <div style="background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%); 
                padding: 16px; border-radius: 12px; margin-bottom: 16px; color: white;">
        <h4 style="margin: 0;">⏳ Human Approval Required</h4>
        <p style="margin: 4px 0 0 0;">The swarm has proposed actions that need your approval before execution.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 📋 Pending Human Approval")
    
    # Info banner
    st.info(f"⚠️ **{len(pending)} action(s) require your approval before execution.**")
    
    # Show each pending action with details
    for i, action in enumerate(pending):
        action_type = action.get("action_type", "UNKNOWN")
        entity_fqn = action.get("target_entity") or action.get("entity_fqn", "unknown")
        parameters = action.get("parameters", {})
        description = strip_think(parameters.get("description", ""))
        confidence = parameters.get("confidence", 0.0)
        
        # Format action type for display
        action_type_display = action_type.replace("_", " ").title()
        
        # Truncate description if too long
        if len(description) > 100:
            description_preview = description[:100] + "..."
        else:
            description_preview = description
        
        confidence_badge = get_confidence_badge(confidence)
        
        with st.expander(f"Action {i+1}: {action_type_display} on {entity_fqn}"):
            st.markdown(f"**Type:** {action_type_display}")
            st.markdown(f"**Target:** `{entity_fqn}`")
            st.markdown(f"**Proposed Change:**")
            st.markdown(f"> {description_preview}")
            st.markdown(f"**Confidence:** {confidence:.0%} {confidence_badge}")
    
    # Approval buttons side by side
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✅ Approve All", type="primary", use_container_width=True):
            try:
                from src.graph.action_executor import execute_pending_actions
                result = execute_pending_actions(pending)
                
                successful = result.get("successful_actions", 0)
                failed = result.get("failed_actions", 0)
                total = result.get("total_actions", 0)
                
                if failed == 0:
                    st.success(f"✅ {successful} action(s) applied successfully!")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"✅ Approved and applied {successful} action(s) to OpenMetadata."
                    })
                else:
                    st.warning(f"⚠️ {successful} succeeded, {failed} failed out of {total} total.")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"⚠️ Approved {total} action(s) - {successful} succeeded, {failed} failed."
                    })
            except Exception as e:
                import traceback
                logger.error(f"Action execution failed: {traceback.format_exc()}")
                st.error(f"Execution failed: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ Failed to execute actions: {str(e)}"
                })
            
            # Mark as processed and clear pending actions
            st.session_state.human_actions_processed = True
            st.session_state.pending_human_actions = []
            st.session_state.pending_approvals = []
            st.rerun()
    
    with col2:
        if st.button("❌ Reject All", type="secondary", use_container_width=True):
            st.info("Actions rejected. No changes will be made to OpenMetadata.")
            st.session_state.messages.append({
                "role": "assistant",
                "content": "❌ Human rejected all pending actions. No changes made."
            })
            
            # Mark as processed and clear pending actions
            st.session_state.human_actions_processed = True
            st.session_state.pending_human_actions = []
            st.session_state.pending_approvals = []
            st.rerun()


def main():
    """Main application entry point."""
    # Initialize session state
    init_session_state()
    
    # Render top bar
    render_top_bar()
    
    # Render sidebar
    render_sidebar()
    
    # Render approval gate prominently if there are pending actions
    render_approval_gate()
    
    # Main content area with tabs
    tab1, tab2, tab3, tab4 = st.tabs(["💬 Chat", "🎭 Swarm Theater", "📈 Execution DAG", "📋 Audit"])
    
    with tab1:
        render_chat_tab()
    
    with tab2:
        render_swarm_theater_tab()
    
    with tab3:
        render_execution_dag_tab()
    
    with tab4:
        render_audit_tab()
    



if __name__ == "__main__":
    main()