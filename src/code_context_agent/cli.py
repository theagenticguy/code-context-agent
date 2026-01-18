"""Command-line interface for code-context-agent.

This module provides the main CLI entry point using cyclopts. It integrates
with the configuration system and Rich display utilities to provide a
user-friendly command-line experience.

Example:
    Run the CLI directly::

        $ python -m code_context_agent.cli
        $ code-context-agent --debug
        $ code-context-agent --output-format=json
        $ code-context-agent analyze /path/to/repo
        $ code-context-agent analyze /path/to/repo --deep
"""

from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, Parameter
from rich.console import Console

from code_context_agent import __version__
from code_context_agent.config import Settings, get_settings
from code_context_agent.display import display_welcome

console = Console()

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


@app.command
def analyze(
    path: Annotated[
        Path,
        Parameter(help="Path to the repository to analyze."),
    ] = Path(),
    *,
    deep: Annotated[
        bool,
        Parameter(help="Enable DEEP mode for comprehensive analysis (~50+ tool calls)."),
    ] = False,
    output_dir: Annotated[
        Path | None,
        Parameter(help="Output directory for context files. Defaults to <repo>/.agent"),
    ] = None,
    focus: Annotated[
        str,
        Parameter(help="Focus area for analysis (e.g., 'authentication', 'API endpoints', 'database layer')."),
    ] = "",
    no_steering: Annotated[
        bool,
        Parameter(help="Disable progressive disclosure steering (enabled by default)."),
    ] = False,
    quiet: Annotated[
        bool,
        Parameter(help="Suppress live display output."),
    ] = False,
    debug: Annotated[
        bool,
        Parameter(help="Enable debug logging for troubleshooting."),
    ] = False,
) -> None:
    """Analyze a codebase and produce a narrated context bundle.

    This command runs the code context analysis agent on the specified
    repository. The agent uses a combination of static analysis tools
    (ripgrep, repomix, ast-grep) and LSP semantic analysis to understand
    the codebase structure and produce a narrated markdown bundle.

    Modes:
        FAST (default): Quick overview for starting work safely.
            ~10-15 tool calls, minimal LSP, 5-15 business logic candidates.

        DEEP (--deep): Thorough analysis for onboarding or safe refactoring.
            ~50+ tool calls, full dependency cones, comprehensive analysis.

    Outputs:
        .agent/CONTEXT.md - The narrated context bundle
        .agent/CONTEXT.orientation.md - Token distribution tree
        .agent/CONTEXT.bundle.md - Curated source code pack

    Example:
        $ code-context-agent analyze /path/to/repo
        $ code-context-agent analyze . --deep
        $ code-context-agent analyze . --output-dir ./output
    """
    import asyncio
    import logging

    from code_context_agent.agent import run_analysis

    # Enable debug logging if requested
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        # Also enable strands debug logging
        logging.getLogger("strands").setLevel(logging.DEBUG)
        logging.getLogger("code_context_agent").setLevel(logging.DEBUG)
        console.print("[dim]Debug logging enabled[/dim]")

    repo_path = path.resolve()

    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise SystemExit(1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise SystemExit(1)

    mode = "deep" if deep else "fast"
    use_steering = not no_steering

    # Show analysis configuration
    if not quiet:
        console.print()
        console.print(f"[bold]Code Context Analysis[/bold]")
        console.print(f"  Repository: [cyan]{repo_path}[/cyan]")
        console.print(f"  Mode: [yellow]{mode.upper()}[/yellow] {'(~50+ tool calls)' if deep else '(~10-15 tool calls)'}")
        if focus:
            console.print(f"  Focus: [magenta]{focus}[/magenta]")
        if use_steering:
            console.print(f"  Steering: [green]enabled[/green] (progressive disclosure)")
        console.print()

    # Run the analysis
    result = asyncio.run(
        run_analysis(
            repo_path=repo_path,
            output_dir=output_dir,
            mode=mode,
            focus=focus or None,
            quiet=quiet,
            use_steering=use_steering,
        )
    )

    # Display results
    if result["status"] == "completed":
        console.print()
        console.print("[green]✓[/green] Analysis completed successfully")
        console.print(f"  Output directory: [cyan]{result['output_dir']}[/cyan]")
        if result.get("context_path"):
            console.print(f"  Context file: [cyan]{result['context_path']}[/cyan]")
    elif result["status"] == "stopped":
        console.print()
        console.print(f"[yellow]⚠[/yellow] Analysis stopped: {result.get('exceeded_limit', 'limit exceeded')}")
        console.print(f"  Turns: {result.get('turn_count', '?')}, Duration: {result.get('duration_seconds', 0):.1f}s")
        if result.get("context_path"):
            console.print(f"  Partial output: [cyan]{result['context_path']}[/cyan]")
        raise SystemExit(1)
    else:
        console.print()
        error = result.get("error") or "Unknown error (no error message captured)"
        console.print(f"[red]✗[/red] Analysis failed: {error}")
        if debug:
            console.print(f"[dim]Status: {result.get('status')}, Turns: {result.get('turn_count', 0)}[/dim]")
        raise SystemExit(1)


if __name__ == "__main__":
    app()
