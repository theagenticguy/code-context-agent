"""Configuration module using pydantic-settings.

This module provides application configuration management through environment
variables using pydantic-settings. Settings are loaded from environment variables
with the CODE_CONTEXT_ prefix and optionally from a .env file.

Example:
    >>> from code_context_agent.config import get_settings
    >>> settings = get_settings()
    >>> print(settings.app_name)
    'code-context-agent'

Environment Variables:
    CODE_CONTEXT_APP_NAME: Application name (default: "code-context-agent")
    CODE_CONTEXT_DEBUG: Enable debug mode (default: False)
    CODE_CONTEXT_LOG_LEVEL: Logging level (default: "INFO")
    CODE_CONTEXT_OUTPUT_FORMAT: Output format - "rich", "json", or "plain" (default: "rich")
    CODE_CONTEXT_MODEL_ID: Bedrock model ID for the agent (default: Opus 4.6)
    CODE_CONTEXT_REGION: AWS region for Bedrock
    CODE_CONTEXT_TEMPERATURE: Model temperature (default 1.0 for thinking)
    CODE_CONTEXT_AGENT_MAX_TURNS: Maximum agent turns before stopping (default: 1000)
    CODE_CONTEXT_AGENT_MAX_DURATION: Maximum agent duration in seconds (default: 1200)
    CODE_CONTEXT_OTEL_DISABLED: Disable OpenTelemetry tracing (default: True)
"""

from __future__ import annotations

import functools
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OUTPUT_DIR = ".code-context"
"""Default output directory name for analysis artifacts."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Settings are loaded from environment variables prefixed with CODE_CONTEXT_
    and optionally from a .env file in the current working directory.

    Attributes:
        app_name: The application name used for identification and logging.
        debug: Enable debug mode for verbose output and additional diagnostics.
        log_level: Logging level for the application logger.
        output_format: Output format for CLI responses.
    """

    model_config = SettingsConfigDict(
        env_prefix="CODE_CONTEXT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(
        default="code-context-agent",
        description="Application name used for identification and logging",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode for verbose output and additional diagnostics",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    output_format: Literal["rich", "json", "plain"] = Field(
        default="rich",
        description="Output format for CLI responses",
    )

    # Agent model settings
    model_id: str = Field(
        default="global.anthropic.claude-opus-4-6-v1",
        description="Bedrock model ID for the analysis agent",
    )
    region: str = Field(
        default="us-east-1",
        description="AWS region for Bedrock API calls",
    )
    temperature: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model temperature (must be 1.0 when thinking is enabled)",
    )

    # Agent execution bounds
    agent_max_turns: int = Field(
        default=1000,
        ge=10,
        le=5000,
        description="Maximum agent turns before stopping",
    )
    agent_max_duration: int = Field(
        default=1200,
        ge=60,
        le=7200,
        description="Maximum agent duration in seconds (default: 20 min)",
    )

    # Full mode execution bounds (overrides agent_max_* when --full is used)
    full_max_duration: int = Field(
        default=3600,
        ge=300,
        le=14400,
        description="Maximum duration in seconds for --full mode (default: 60 min)",
    )
    full_max_turns: int = Field(
        default=3000,
        ge=100,
        le=10000,
        description="Maximum turns for --full mode",
    )

    # Team (swarm) timeout bounds — used as defaults when the coordinator
    # does not pass explicit values to dispatch_team.
    team_execution_timeout: int = Field(
        default=900,
        ge=120,
        le=7200,
        description="Max seconds for entire team swarm execution (standard mode)",
    )
    team_node_timeout: int = Field(
        default=900,
        ge=120,
        le=7200,
        description="Max seconds per agent node within a team (standard mode)",
    )
    full_team_execution_timeout: int = Field(
        default=2400,
        ge=300,
        le=14400,
        description="Max seconds for entire team swarm execution (--full mode)",
    )
    full_team_node_timeout: int = Field(
        default=1800,
        ge=300,
        le=14400,
        description="Max seconds per agent node within a team (--full mode)",
    )

    # MCP tool sources for the analysis agent
    gitnexus_enabled: bool = Field(
        default=True,
        description="Enable GitNexus MCP server for structural code intelligence during analysis",
    )
    context7_enabled: bool = Field(
        default=True,
        description="Enable context7 MCP server for library documentation lookup during analysis",
    )

    # Reasoning effort level for the analysis agent
    reasoning_effort: Literal["low", "medium", "high", "max"] = Field(
        default="high",
        description="Reasoning effort level: 'high' (default standard), 'max' (full mode default, Opus only)",
    )
    full_reasoning_effort: Literal["low", "medium", "high", "max"] = Field(
        default="max",
        description="Reasoning effort level for --full mode (default: 'max', Opus 4.6 only)",
    )

    # Telemetry settings
    otel_disabled: bool = Field(
        default=True,
        description="Disable OpenTelemetry tracing to avoid context detachment errors",
    )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings instance (cached singleton).

    Returns the same Settings instance on subsequent calls. Settings are
    loaded from environment variables and the optional .env file on first call.

    Call ``get_settings.cache_clear()`` if you need to reload from environment
    (e.g., in tests).

    Returns:
        Settings instance loaded from environment.

    Example:
        >>> settings = get_settings()
        >>> settings.debug
        False
        >>> settings.log_level
        'INFO'
    """
    return Settings()
