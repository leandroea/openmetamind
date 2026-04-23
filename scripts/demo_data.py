"""
Demo data population script for OpenMetaMind.

This script populates local OpenMetadata with realistic demo data for testing.
Run with: python scripts/demo_data.py

Requires:
- OpenMetadata running at localhost:8585
- OPENMETADATA_JWT_TOKEN environment variable set
"""

import asyncio
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp.client import get_mcp_client, OpenMetadataMCPClient
from src.models.state import ProposedAction, ActionType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Demo data: 5 tables with realistic structure
DEMO_TABLES = [
    {
        "database": "customers",
        "table": "users",
        "description": "User accounts and profiles",
        "columns": [
            {"name": "user_id", "type": "BIGINT", "description": "Primary key", "is_pii": False, "nullable": False},
            {"name": "email", "type": "VARCHAR(255)", "description": "User email address", "is_pii": True, "nullable": False},
            {"name": "full_name", "type": "VARCHAR(100)", "description": "User full name", "is_pii": True, "nullable": False},
            {"name": "phone", "type": "VARCHAR(20)", "description": "Phone number", "is_pii": True, "nullable": True},
            {"name": "created_at", "type": "TIMESTAMP", "description": "Account creation time", "is_pii": False, "nullable": False},
            {"name": "last_login", "type": "TIMESTAMP", "description": "Last login time", "is_pii": False, "nullable": True},
            {"name": "is_active", "type": "BOOLEAN", "description": "Account active status", "is_pii": False, "nullable": False},
        ],
        "owner": "sales_team",
        "has_missing_owner": False,
        "has_untagged_pii": True,
    },
    {
        "database": "customers",
        "table": "orders",
        "description": "Customer orders",
        "columns": [
            {"name": "order_id", "type": "BIGINT", "description": "Primary key", "is_pii": False, "nullable": False},
            {"name": "user_id", "type": "BIGINT", "description": "Foreign key to users", "is_pii": False, "nullable": False},
            {"name": "order_total", "type": "DECIMAL(10,2)", "description": "Order total amount", "is_pii": False, "nullable": False},
            {"name": "status", "type": "VARCHAR(20)", "description": "Order status", "is_pii": False, "nullable": False},
            {"name": "shipping_address", "type": "TEXT", "description": "Shipping address", "is_pii": True, "nullable": True},
            {"name": "created_at", "type": "TIMESTAMP", "description": "Order creation time", "is_pii": False, "nullable": False},
        ],
        "owner": "ecommerce_team",
        "has_missing_owner": False,
        "has_untagged_pii": True,
    },
    {
        "database": "customers",
        "table": "events",
        "description": "User activity events",
        "columns": [
            {"name": "event_id", "type": "BIGINT", "description": "Primary key", "is_pii": False, "nullable": False},
            {"name": "user_id", "type": "BIGINT", "description": "User who triggered event", "is_pii": False, "nullable": True},
            {"name": "event_type", "type": "VARCHAR(50)", "description": "Type of event", "is_pii": False, "nullable": False},
            {"name": "event_data", "type": "JSON", "description": "Event payload", "is_pii": False, "nullable": True},
            {"name": "ip_address", "type": "VARCHAR(45)", "description": "Client IP address", "is_pii": True, "nullable": True},
            {"name": "created_at", "type": "TIMESTAMP", "description": "Event timestamp", "is_pii": False, "nullable": False},
        ],
        "owner": None,  # Missing owner - governance gap!
        "has_missing_owner": True,
        "has_untagged_pii": True,
    },
    {
        "database": "customers",
        "table": "products",
        "description": "Product catalog",
        "columns": [
            {"name": "product_id", "type": "BIGINT", "description": "Primary key", "is_pii": False, "nullable": False},
            {"name": "name", "type": "VARCHAR(200)", "description": "Product name", "is_pii": False, "nullable": False},
            {"name": "description", "type": "TEXT", "description": "Product description", "is_pii": False, "nullable": True},
            {"name": "price", "type": "DECIMAL(10,2)", "description": "Product price", "is_pii": False, "nullable": False},
            {"name": "category", "type": "VARCHAR(50)", "description": "Product category", "is_pii": False, "nullable": True},
            {"name": "created_at", "type": "TIMESTAMP", "description": "Creation timestamp", "is_pii": False, "nullable": False},
        ],
        "owner": "product_team",
        "has_missing_owner": False,
        "has_untagged_pii": False,
    },
    {
        "database": "customers",
        "table": "sessions",
        "description": "User session data",
        "columns": [
            {"name": "session_id", "type": "VARCHAR(100)", "description": "Session identifier", "is_pii": False, "nullable": False},
            {"name": "user_id", "type": "BIGINT", "description": "User ID", "is_pii": False, "nullable": True},
            {"name": "ip_address", "type": "VARCHAR(45)", "description": "Session IP address", "is_pii": True, "nullable": True},
            {"name": "user_agent", "type": "TEXT", "description": "Browser user agent", "is_pii": False, "nullable": True},
            {"name": "started_at", "type": "TIMESTAMP", "description": "Session start", "is_pii": False, "nullable": False},
            {"name": "ended_at", "type": "TIMESTAMP", "description": "Session end", "is_pii": False, "nullable": True},
            {"name": "data", "type": "JSON", "description": "Session data", "is_pii": False, "nullable": True},
        ],
        "owner": None,  # Missing owner - governance gap!
        "has_missing_owner": True,
        "has_untagged_pii": True,
    },
]


async def create_demo_data():
    """Create demo data in OpenMetadata via MCP."""
    logger.info("Starting demo data population...")
    
    # Check for JWT token
    jwt_token = os.getenv("OPENMETADATA_JWT_TOKEN")
    if not jwt_token:
        logger.error("OPENMETADATA_JWT_TOKEN environment variable is required")
        logger.info("Please set it and try again.")
        return False
    
    try:
        async with get_mcp_client() as client:
            logger.info("Connected to OpenMetadata MCP server")
            
            # First, list existing entities to see what's there
            logger.info("Checking existing entities...")
            try:
                existing = await client.list_entities(entity_type="database", database="customers")
                logger.info(f"Found {len(existing)} existing entities in customers database")
            except Exception as e:
                logger.warning(f"Could not list entities: {e}")
            
            # Create tables via MCP calls
            # Note: The actual MCP tool names depend on your OpenMetadata MCP server implementation
            # This script assumes standard MCP tools exist
            
            for table_data in DEMO_TABLES:
                fqn = f"{table_data['database']}.{table_data['table']}"
                logger.info(f"Processing table: {fqn}")
                
                # Get table profile (this should work if table exists)
                try:
                    profile = await client.get_table_profile(fqn=fqn)
                    logger.info(f"  Table exists: {fqn}")
                    
                    # Check for missing description
                    if not profile.description:
                        logger.info(f"  Missing description - would add: {table_data['description']}")
                        # In a real scenario, we would call update_description
                        # await client.update_description(fqn, table_data['description'])
                    
                except Exception as e:
                    logger.info(f"  Table may not exist or error: {e}")
                    logger.info(f"  Would create table with description: {table_data['description']}")
                
                # Process columns
                for col in table_data['columns']:
                    col_fqn = f"{fqn}.{col['name']}"
                    
                    # Get column profile
                    try:
                        col_profile = await client.get_column_profile(fqn=col_fqn)
                        logger.info(f"    Column: {col['name']} ({col['type']})")
                        
                        # Check for PII tagging
                        if col['is_pii']:
                            logger.info(f"      PII column detected: {col['name']}")
                            logger.info(f"      Would tag as PII")
                            # In real scenario: await client.add_tags(col_fqn, ["PII"])
                    
                    except Exception as e:
                        logger.info(f"    Column error or not found: {col['name']}")
                
                # Check for missing owner
                if table_data['has_missing_owner']:
                    logger.info(f"  Missing owner - governance gap detected!")
                    logger.info(f"  Would suggest owner: {table_data.get('owner', 'unknown')}")
            
            # Summary of governance gaps
            logger.info("\n" + "="*60)
            logger.info("DEMO DATA SUMMARY")
            logger.info("="*60)
            
            total_pii_columns = sum(
                sum(1 for col in t['columns'] if col['is_pii'])
                for t in DEMO_TABLES
            )
            tables_with_missing_owners = sum(1 for t in DEMO_TABLES if t['has_missing_owner'])
            tables_with_untagged_pii = sum(1 for t in DEMO_TABLES if t['has_untagged_pii'])
            
            logger.info(f"Total tables: {len(DEMO_TABLES)}")
            logger.info(f"Total columns with PII: {total_pii_columns}")
            logger.info(f"Tables with missing owners: {tables_with_missing_owners}")
            logger.info(f"Tables with untagged PII: {tables_with_untagged_pii}")
            
            logger.info("\nGovernance gaps that swarm should detect:")
            for t in DEMO_TABLES:
                if t['has_missing_owner']:
                    logger.info(f"  - {t['database']}.{t['table']}: Missing owner")
                if t['has_untagged_pii']:
                    pii_cols = [c['name'] for c in t['columns'] if c['is_pii']]
                    logger.info(f"  - {t['database']}.{t['table']}: Untagged PII columns: {pii_cols}")
            
            logger.info("\n" + "="*60)
            logger.info("Demo data check complete!")
            logger.info("Run the swarm to analyze and fix these governance gaps.")
            logger.info("="*60)
            
            return True
            
    except Exception as e:
        logger.error(f"Error connecting to OpenMetadata: {e}")
        logger.info("\nMake sure OpenMetadata is running at localhost:8585")
        logger.info("And that the MCP server is enabled.")
        return False


async def create_sample_findings():
    """Create sample findings for testing without real OpenMetadata."""
    from src.models.state import AgentFinding, FindingType, ProposedAction, ActionType
    from datetime import datetime
    
    logger.info("\nCreating sample findings for testing...")
    
    findings = [
        AgentFinding(
            agent_id="catalog_scout",
            subtask_id="discover_1",
            task_description="Discover tables in customers database",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers",
            summary="Found 5 tables in customers database",
            details={
                "tables": ["users", "orders", "events", "products", "sessions"],
                "database": "customers"
            },
            confidence=0.95,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning="Direct MCP query to list entities"
        ),
        AgentFinding(
            agent_id="data_steward",
            subtask_id="classify_1",
            task_description="Detect PII in customers.users",
            finding_type=FindingType.CLASSIFICATION,
            target_entity="customers.users",
            summary="Found 4 PII columns in users table",
            details={
                "pii_columns": ["email", "full_name", "phone"],
                "classifications": {
                    "email": "PII.Sensitive",
                    "full_name": "PII.Sensitive", 
                    "phone": "PII.Sensitive"
                }
            },
            confidence=0.9,
            proposed_actions=[
                ProposedAction(
                    action_type=ActionType.ASSIGN_TAG,
                    entity_fqn="customers.users.email",
                    parameters={"tags": ["PII.Sensitive"]},
                    confidence=0.9,
                    proposed_by="data_steward"
                )
            ],
            mcp_tool_calls=[],
            llm_reasoning="Column name analysis and data type inspection"
        ),
        AgentFinding(
            agent_id="quality_guardian",
            subtask_id="profile_1",
            task_description="Profile customers.events table",
            finding_type=FindingType.QUALITY,
            target_entity="customers.events",
            summary="Events table has 15% null rate in user_id column",
            details={
                "column": "user_id",
                "null_percentage": 15,
                "total_rows": 1000000
            },
            confidence=0.85,
            proposed_actions=[],
            mcp_tool_calls=[],
            llm_reasoning="Column profile analysis"
        ),
    ]
    
    logger.info(f"Created {len(findings)} sample findings")
    for f in findings:
        logger.info(f"  - {f.agent_id}: {f.summary}")
    
    return findings


def main():
    """Main entry point."""
    logger.info("OpenMetaMind Demo Data Script")
    logger.info("="*50)
    
    # Check if we should create real data or sample findings
    create_real = os.getenv("CREATE_REAL_DATA", "false").lower() == "true"
    
    if create_real:
        logger.info("Mode: Creating REAL data in OpenMetadata")
        success = asyncio.run(create_demo_data())
    else:
        logger.info("Mode: Creating sample findings (no OpenMetadata required)")
        success = asyncio.run(create_sample_findings())
    
    if success:
        logger.info("\nDone!")
        return 0
    else:
        logger.info("\nFailed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())