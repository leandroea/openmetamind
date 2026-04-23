"""
Pydantic models for OpenMetadata MCP responses.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class Entity(BaseModel):
    """Represents an OpenMetadata entity (table, database, etc)."""
    id: str
    name: str
    fullyQualifiedName: str
    description: Optional[str] = None
    # Add more fields as needed based on OpenMetadata API


class TableProfile(BaseModel):
    """Table profile data from OpenMetadata."""
    tableName: str
    databaseName: str
    columnCount: int
    rowCount: Optional[int] = None
    size: Optional[int] = None
    created: Optional[datetime] = None
    lastUpdated: Optional[datetime] = None
    # Add more profile fields as needed


class ColumnProfile(BaseModel):
    """Column profile data from OpenMetadata."""
    columnName: str
    dataType: str
    description: Optional[str] = None
    # Add more profile fields as needed


class UsageStats(BaseModel):
    """Usage statistics for an entity."""
    entityFQN: str
    totalQueries: int
    uniqueUsers: int
    lastUpdated: datetime
    # Add more usage fields as needed