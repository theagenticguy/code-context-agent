"""Exception hierarchy for code-context-agent."""


class CodeContextAgentError(Exception):
    """Base exception for all code-context-agent errors."""


class SubprocessError(CodeContextAgentError):
    """Subprocess execution failed."""

    def __init__(self, cmd: str, exit_code: int, stderr: str):
        """Initialize SubprocessError with command details."""
        self.cmd = cmd
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"Command failed (exit code {exit_code}): {cmd}")


class JSONParseError(CodeContextAgentError):
    """Failed to parse JSON output."""


class ValidationError(CodeContextAgentError):
    """Input validation failed."""


class ToolExecutionError(CodeContextAgentError):
    """Tool execution failed."""
