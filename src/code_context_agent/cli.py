"""Command-line interface for code-context-agent.

This module provides the main CLI entry point using cyclopts. It integrates
with the configuration system and Rich display utilities to provide a
user-friendly command-line experience.

Example:
    Run the CLI directly::

        $ python -m code_context_agent.cli
        $ code-context-agent --debug
        $ code-context-agent --output-format=json
"""

from typing import Annotated, Literal

from cyclopts import App, Parameter

from code_context_agent import __version__
from code_context_agent.config import Settings, get_settings
from code_context_agent.display import display_welcome

app = App(
    name="code-context-agent",
    help="A CLI tool for code context analysis.",
    version=__version__,
)


@app.default
def main(
    debug: Annotated[bool, Parameter(help="Enable debug mode.")] = False,
    output_format: Annotated[
        Literal["rich", "json", "plain"], Parameter(help="Output format: rich, json, plain.")
    ] = "rich",
) -> None:
    """Run the code-context-agent CLI.

    This is the main entry point for the CLI. It loads settings from the
    environment and displays a welcome message with current configuration.

    Args:
        debug: Enable debug output for verbose logging and diagnostics.
        output_format: Format for output display. Supported values are
            "rich" (default), "json", or "plain".
    """
    settings = get_settings()
    if debug or output_format != "rich":
        settings = Settings(debug=debug, output_format=output_format)

    display_welcome(settings)


if __name__ == "__main__":
    app()
