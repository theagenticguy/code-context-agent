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
    CODE_CONTEXT_LSP_TS_COMMAND: Command to start TypeScript LSP
    CODE_CONTEXT_LSP_PY_COMMAND: Command to start Python LSP (ty server)
    CODE_CONTEXT_LSP_SERVERS: LSP server commands by language key (JSON dict)
    CODE_CONTEXT_LSP_TIMEOUT: LSP operation timeout in seconds
    CODE_CONTEXT_LSP_STARTUP_TIMEOUT: Maximum seconds to wait for LSP server to initialize
    CODE_CONTEXT_LSP_MAX_FILES: Maximum files before LSP analysis is skipped
    CODE_CONTEXT_AGENT_MAX_TURNS: Maximum agent turns before stopping (default: 1000)
    CODE_CONTEXT_AGENT_MAX_DURATION: Maximum agent duration in seconds (default: 1200)
    CODE_CONTEXT_OTEL_DISABLED: Disable OpenTelemetry tracing (default: True)
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # LSP settings
    lsp_ts_command: str = Field(
        default="typescript-language-server --stdio",
        description="Command to start TypeScript/JavaScript LSP server",
    )
    lsp_py_command: str = Field(
        default="ty server",
        description="Command to start Python LSP server (ty from astral.sh)",
    )
    lsp_servers: dict[str, str] = Field(
        default={
            "ts": "typescript-language-server --stdio",
            "typescript": "typescript-language-server --stdio",
            "py": "ty server",
            "python": "ty server",
            "rust": "rust-analyzer",
            "go": "gopls serve",
            "java": "jdtls",
        },
        description="Mapping of language identifiers to LSP server commands",
    )
    lsp_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout in seconds for LSP operations",
    )
    lsp_startup_timeout: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Maximum seconds to wait for LSP server to initialize",
    )
    lsp_max_files: int = Field(
        default=5000,
        ge=100,
        le=50000,
        description="Maximum files before LSP analysis is skipped",
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

    # Telemetry settings
    otel_disabled: bool = Field(
        default=True,
        description="Disable OpenTelemetry tracing to avoid context detachment errors",
    )


def get_settings() -> Settings:
    """Get application settings instance.

    Creates and returns a new Settings instance with values loaded from
    environment variables and the optional .env file.

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
