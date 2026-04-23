"""
Configuration settings for OpenMetaMind.

Uses Pydantic Settings to load configuration from environment variables.
"""

from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All configuration is read from .env file - no hardcoded project defaults.
    """
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'  # Ignore extra env vars
    )
    
    # OpenMetadata MCP Server
    openmetadata_mcp_url: str = Field(
        description="URL of the OpenMetadata MCP server"
    )
    openmetadata_jwt_token: str = Field(
        description="JWT token for OpenMetadata authentication"
    )
    
    # NVIDIA LLM API
    nvidia_api_key: str = Field(
        description="API key for NVIDIA's LLM API"
    )
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="Base URL for NVIDIA API"
    )
    llm_model: str = Field(
        default="minimax/minimax-m2.5",
        description="LLM model to use"
    )
    
    # Database
    database_url: str = Field(
        default="sqlite:///checkpoints.db",
        description="Database connection string for checkpointing"
    )
    
    # Slack Integration (optional)
    slack_bot_token: Optional[str] = Field(
        default=None,
        description="Slack bot token"
    )
    slack_signing_secret: Optional[str] = Field(
        default=None,
        description="Slack signing secret"
    )
    slack_app_token: Optional[str] = Field(
        default=None,
        description="Slack app-level token for Socket Mode"
    )
    
    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    @field_validator('openmetadata_mcp_url')
    @classmethod
    def validate_mcp_url(cls, v: str) -> str:
        """Ensure the MCP URL ends with /mcp."""
        if not v.endswith('/mcp'):
            # Try to append /mcp if not present
            if '/mcp' not in v:
                v = v.rstrip('/') + '/mcp'
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v
    
    @property
    def mcp_base_url(self) -> str:
        """Get the base URL for MCP (without /mcp suffix)."""
        return self.openmetadata_mcp_url.rstrip('/mcp').rstrip('/')
    
    def get_llm_config(self) -> dict:
        """Get LLM configuration for ChatOpenAI."""
        return {
            "base_url": self.nvidia_base_url,
            "api_key": self.nvidia_api_key,
            "model": self.llm_model,
            "temperature": 0.1,
            "max_tokens": 1000
        }


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings