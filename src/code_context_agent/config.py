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
