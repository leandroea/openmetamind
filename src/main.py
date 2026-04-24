"""
FastAPI backend for OpenMetaMind.

Provides REST API and WebSocket endpoints for interacting with the swarm.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_settings, setup_logging
from .graph.swarm_graph import build_swarm_graph, get_swarm_graph
from .graph.nodes import coordinator, planner, dispatcher, integrity_critic, action_executor_node
from .agents.registry import AgentRegistry
from .mcp.client import OpenMetadataMCPClient

# Initialize logging from settings
setup_logging()
logger = logging.getLogger(__name__)

# Global variables for the app state
swarm_graph = None
checkpointer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Initializes resources on startup and cleans up on shutdown.
    """
    global swarm_graph, checkpointer
    
    # Load settings
    settings = get_settings()
    logger.info("Starting OpenMetaMind backend...")
    logger.info(f"MCP URL: {settings.openmetadata_mcp_url}")
    logger.info(f"LLM Model: {settings.llm_model}")
    
    # AgentRegistry auto-registers agents on import, so we just need to ensure
    # the agents are imported. We'll import the agents module to trigger registration.
    import src.agents  # This will trigger agent registration via __init__.py
    logger.info("Agent registry initialized with %d agents", 
                len(AgentRegistry().list_agents()))
    
    # Build the swarm graph with a checkpointer
    swarm_graph = build_swarm_graph()
    logger.info("Swarm graph built successfully")
    
    yield
    
    # Cleanup: close any resources if needed
    logger.info("Shutting down OpenMetaMind backend...")
    # Note: Our MCP client is used per-call as an async context manager,
    # so there's no global client to close.
    # If we had a global client, we would close it here.
    swarm_graph = None
    logger.info("Backend shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="OpenMetaMind API",
    description="Autonomous multi-agent swarm for OpenMetadata data governance",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for API requests/responses
class SwarmQuery(BaseModel):
    query: str
    user_id: str
    session_id: Optional[str] = None


class SwarmResponse(BaseModel):
    session_id: str
    coordinator_response: Optional[str] = None
    blackboard_summary: Dict[str, Any]
    approved_actions: List[Dict[str, Any]]
    execution_results: Optional[Dict[str, Any]] = None


class AgentInfo(BaseModel):
    agent_id: str
    display_name: str
    description: str
    avatar_emoji: str
    capabilities: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    mcp_connection: str
    version: str = "0.1.0"


class ApproveRequest(BaseModel):
    session_id: str
    action_ids: List[str]
    decision: str  # "approve" or "reject"


# Dependency to get the swarm graph
def get_graph():
    if swarm_graph is None:
        raise HTTPException(status_code=503, detail="Swarm graph not initialized")
    return swarm_graph


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    
    # Test MCP connection by trying to create a client (but not actually connecting)
    try:
        # We don't want to actually make a call in health check to avoid delays
        # Just check if the client can be instantiated
        client = OpenMetadataMCPClient(
            base_url=settings.openmetadata_mcp_url,
            jwt_token=settings.openmetadata_jwt_token
        )
        # We won't actually connect because that would require async context
        mcp_status = "configured"
    except Exception as e:
        mcp_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy",
        mcp_connection=mcp_status
    )


@app.post("/api/swarm/run", response_model=SwarmResponse)
async def run_swarm(query: SwarmQuery, graph=Depends(get_graph)):
    """Run a swarm query and return the results."""
    # Initialize SwarmState
    initial_state = {
        "user_query": query.query,
        "user_input": query.query,  # For backward compatibility
        "conversation_history": [],  # Start with empty history
        # Other fields will be filled by the graph
    }
    
    # Use the provided session_id or generate a new one
    session_id = query.session_id or f"session_{os.urandom(4).hex()}"
    
    # Configure the graph with a thread ID for checkpointing
    config = {"configurable": {"thread_id": session_id}}
    
    try:
        # Execute the graph
        final_state = await graph.ainvoke(initial_state, config=config)
        
        # Debug: Log the final state keys and findings
        logger.info(f"Final state keys: {list(final_state.keys())}")
        logger.info(f"Findings in state: {len(final_state.get('findings', []))}")
        
        # Extract response data
        coordinator_response = final_state.get("coordinator_response")
        blackboard = final_state.get("blackboard", {})
        # Findings and agent_statuses are at top level with operator.add for accumulation
        findings = final_state.get("findings", [])
        agent_statuses = final_state.get("agent_statuses", {})
        approved_actions = final_state.get("approved_actions", [])
        execution_results = final_state.get("action_results")
        
        # If coordinator_response is None but we have findings, generate a summary
        if coordinator_response is None and findings:
            # Build a response from findings
            if isinstance(findings, list) and len(findings) > 0:
                summary_parts = []
                for f in findings[:5]:  # Limit to first 5 findings
                    if isinstance(f, dict):
                        summary = f.get("summary", "")
                        if summary:
                            summary_parts.append(summary)
                    else:
                        summary = getattr(f, 'summary', '')
                        if summary:
                            summary_parts.append(summary)
                
                if summary_parts:
                    coordinator_response = "I found the following information:\n\n" + "\n".join(f"- {s}" for s in summary_parts)
                    if len(findings) > 5:
                        coordinator_response += f"\n\n...and {len(findings) - 5} more findings."
                else:
                    # Even if no summary, still generate a response
                    coordinator_response = f"The swarm completed analysis with {len(findings)} finding(s). Check the findings panel for details."
            else:
                coordinator_response = "The swarm has completed its analysis."
        
        # Create a summary of the blackboard
        blackboard_summary = {
            "findings": findings,  # Include actual findings for UI display
            "findings_count": len(findings),
            "conflicts": blackboard.get("conflicts", []) if isinstance(blackboard, dict) else [],
            "conflicts_count": len(blackboard.get("conflicts", [])) if isinstance(blackboard, dict) else 0,
            "agent_statuses": agent_statuses,
            "execution_phase": blackboard.get("execution_phase", "unknown") if isinstance(blackboard, dict) else "unknown"
        }
        
        return SwarmResponse(
            session_id=session_id,
            coordinator_response=coordinator_response,
            blackboard_summary=blackboard_summary,
            approved_actions=approved_actions,
            execution_results=execution_results
        )
        
    except Exception as e:
        logger.error(f"Error running swarm: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/swarm/status/{session_id}")
async def get_swarm_status(session_id: str, graph=Depends(get_graph)):
    """Get the current state of a swarm session."""
    config = {"configurable": {"thread_id": session_id}}
    
    try:
        # Get the current state from the checkpointer
        state = await graph.aget_state(config)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return state.values  # Return the state values
        
    except Exception as e:
        logger.error(f"Error getting swarm status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents", response_model=List[AgentInfo])
async def list_agents():
    """List all registered agents with their capabilities."""
    registry = AgentRegistry()
    agents = registry.list_agents()
    
    agent_info_list = []
    for agent in agents:
        capabilities = []
        for cap in agent.capabilities:
            capabilities.append({
                "name": cap.name,
                "description": cap.description,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema
            })
        
        agent_info_list.append(AgentInfo(
            agent_id=agent.agent_id,
            display_name=agent.display_name,
            description=agent.description,
            avatar_emoji=agent.avatar_emoji,
            capabilities=capabilities
        ))
    
    return agent_info_list


@app.websocket("/ws/swarm/{session_id}")
async def swarm_websocket(websocket: WebSocket, session_id: str, graph=Depends(get_graph)):
    """WebSocket endpoint for real-time swarm execution updates."""
    await websocket.accept()
    
    try:
        # Wait for the initial query message
        data = await websocket.receive_text()
        query_data = json.loads(data)
        query = query_data.get("query", "")
        user_id = query_data.get("user_id", "anonymous")
        
        if not query:
            await websocket.send_json({
                "type": "error",
                "data": {"message": "Query is required"}
            })
            await websocket.close()
            return
        
        # Initialize SwarmState
        initial_state = {
            "user_query": query,
            "user_input": query,
            "conversation_history": [],
        }
        
        # Configure the graph with a thread ID for checkpointing
        config = {"configurable": {"thread_id": session_id}}
        
        # Stream the graph execution
        async for event in graph.astream(initial_state, config=config, stream_mode=["updates", "custom"]):
            # event is a tuple (node_name, state_update) for "updates"
            # or just the custom data for "custom"
            if isinstance(event, tuple) and len(event) == 2:
                node_name, state_update = event
                # Determine what type of update this is
                if node_name == "coordinator":
                    msg_type = "coordinator_update"
                elif node_name == "planner":
                    msg_type = "planner_update"
                elif node_name == "dispatcher":
                    msg_type = "dispatcher_update"
                elif node_name == "agent_executor":
                    msg_type = "agent_update"
                elif node_name == "integrity_critic":
                    msg_type = "critic_update"
                elif node_name == "action_executor":
                    msg_type = "action_update"
                else:
                    msg_type = "node_update"
                
                await websocket.send_json({
                    "type": msg_type,
                    "node": node_name,
                    "data": state_update
                })
            else:
                # Custom event
                await websocket.send_json({
                    "type": "custom",
                    "data": event
                })
        
        # Send completion signal
        await websocket.send_json({
            "type": "complete",
            "data": {"message": "Swarm execution finished"}
        })
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)}
            })
        except:
            pass  # Ignore errors when trying to send error message
    finally:
        try:
            await websocket.close()
        except:
            pass


@app.post("/api/swarm/approve")
async def approve_actions(request: ApproveRequest, graph=Depends(get_graph)):
    """Resume graph execution after human approval by updating state and re-invoking."""
    config = {"configurable": {"thread_id": request.session_id}}
    
    try:
        # Get the current state
        state = await graph.aget_state(config)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")
        
        current_state = state.values
        
        # Update the state based on the decision
        if request.decision == "approve":
            # In a real implementation, we would move approved actions to be executed
            # For now, we'll just signal to continue to action execution
            # The integrity critic would have already set the next step
            pass
        elif request.decision == "reject":
            # Reject all actions and go back to planner for retry
            current_state["next"] = "planner"
            # Clear approved actions
            current_state["approved_actions"] = []
        else:
            raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'")
        
        # Re-invoke the graph from the current state
        final_state = await graph.ainvoke(current_state, config=config)
        
        return {
            "session_id": request.session_id,
            "message": f"Actions {request.decision}d successfully",
            "state": final_state
        }
        
    except Exception as e:
        logger.error(f"Error processing approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # For running directly with uvicorn
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)