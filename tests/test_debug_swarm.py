"""Debug test for full swarm graph with real MCP."""
import pytest
import asyncio
from src.ui.swarm_runner import SwarmRunner

def test_swarm_runner_query_building():
    """Test the SwarmRunner directly with the same query from Streamlit."""
    runner = SwarmRunner()
    
    # This is the exact query the user types in Streamlit
    result = runner.run("list all the tables in the catalog", session_id="test_debug_001")
    
    print(f"\nSwarm Runner Result:")
    print(f"  Session ID: {result.get('session_id')}")
    print(f"  Coordinator response: {result.get('coordinator_response', 'NONE')[:200]}...")
    print(f"  Blackboard summary: {result.get('blackboard_summary')}")
    print(f"  Findings count: {result.get('blackboard_summary', {}).get('findings_count', 0)}")
    
    # Check findings
    findings = result.get('blackboard_summary', {}).get('findings', [])
    if findings:
        for i, f in enumerate(findings[:3]):
            if isinstance(f, dict):
                print(f"  Finding {i+1}: {f.get('summary', 'no summary')}")
                print(f"    Details: {f.get('details', {})}")
            else:
                print(f"  Finding {i+1}: {getattr(f, 'summary', 'no summary')}")


if __name__ == "__main__":
    test_swarm_runner_query_building()
    print("\nDone")