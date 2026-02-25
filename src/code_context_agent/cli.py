"""Command-line interface for code-context-agent.

This module provides the main CLI entry point using cyclopts.

Example:
    $ code-context-agent analyze /path/to/repo
    $ code-context-agent analyze /path/to/repo --focus "authentication"
    $ code-context-agent analyze . --quiet
    $ code-context-agent analyze . --issue "gh:1694"
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
        Literal["rich", "json", "plain"],
        Parameter(help="Output format: rich, json, plain."),
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
    output_dir: Annotated[
        Path | None,
        Parameter(help="Output directory for context files. Defaults to <repo>/.agent"),
    ] = None,
    focus: Annotated[
        str,
        Parameter(help="Focus area for analysis (e.g., 'authentication', 'API endpoints', 'database layer')."),
    ] = "",
    issue: Annotated[
        str,
        Parameter(help="Issue reference for focused analysis (e.g., 'gh:1694', 'gh:owner/repo#1694')."),
    ] = "",
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

    The agent uses LSP, AST-grep, ripgrep, repomix, and git history
    tools to understand the codebase, then produces a narrated markdown
    bundle. Analysis depth is determined automatically based on repository
    size and complexity.

    Outputs:
        .agent/CONTEXT.md - The narrated context bundle
        .agent/CONTEXT.orientation.md - Token distribution tree
        .agent/CONTEXT.bundle.md - Curated source code pack

    Example:
        $ code-context-agent analyze /path/to/repo
        $ code-context-agent analyze . --focus "authentication"
        $ code-context-agent analyze . --output-dir ./output
        $ code-context-agent analyze . --issue "gh:1694"
    """
    import asyncio

    from loguru import logger

    from code_context_agent.agent import run_analysis
    from code_context_agent.utils import setup_logger

    # Configure logging: suppress loguru in normal mode (Rich Live conflict),
    # enable full logging in debug mode (which uses QuietConsumer instead)
    if debug:
        setup_logger(level="DEBUG")
        console.print("[dim]Debug logging enabled (live display disabled)[/dim]")
    else:
        # Remove default loguru handler to prevent stderr writes that break Rich Live
        logger.remove()
        setup_logger(level="WARNING")

    repo_path = path.resolve()

    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise SystemExit(1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise SystemExit(1)

    # Show analysis configuration
    if not quiet:
        console.print()
        console.print("[bold]Code Context Analysis[/bold]")
        console.print(f"  Repository: [cyan]{repo_path}[/cyan]")
        if focus:
            console.print(f"  Focus: [magenta]{focus}[/magenta]")
        console.print()

    # In debug mode, use quiet consumer (log output replaces Live display)
    use_quiet = quiet or debug

    # Fetch issue context if provided (deterministic, not model-invoked)
    issue_context = None
    if issue:
        from code_context_agent.issues import render_issue_context
        from code_context_agent.issues.github import GitHubIssueProvider, parse_issue_ref

        try:
            provider_name, issue_ref = parse_issue_ref(issue)
            if provider_name == "gh":
                provider = GitHubIssueProvider()
                fetched_issue = provider.fetch(issue_ref)
                issue_context = render_issue_context(fetched_issue)
                if not use_quiet:
                    console.print(f"  Issue: [magenta]{fetched_issue.title}[/magenta]")
            else:
                console.print(f"[yellow]Warning:[/yellow] Unsupported issue provider: {provider_name}")
        except RuntimeError as e:
            console.print(f"[yellow]Warning:[/yellow] Could not fetch issue: {e}")

    # Run the analysis
    result = asyncio.run(
        run_analysis(
            repo_path=repo_path,
            output_dir=output_dir,
            focus=focus or None,
            quiet=use_quiet,
            issue_context=issue_context,
        ),
    )

    _display_result(result, debug=debug)


@app.command
def viz(  # noqa: C901, PLR0915
    path: Annotated[
        Path,
        Parameter(help="Path to the repository (must contain .agent/ output)."),
    ] = Path(),
    *,
    output_dir: Annotated[
        Path | None,
        Parameter(help="Output directory containing analysis results. Defaults to <path>/.agent"),
    ] = None,
    port: Annotated[
        int,
        Parameter(help="Port for the local HTTP server."),
    ] = 8765,
    no_open: Annotated[
        bool,
        Parameter(help="Don't auto-open the browser."),
    ] = False,
) -> None:
    """Launch an interactive visualization of analysis results.

    Serves a local web UI that displays the code graph, modules,
    hotspots, dependency chains, and the CONTEXT.md narrative.

    Requires a prior `analyze` run to generate .agent/ output files.

    Example:
        $ code-context-agent viz /path/to/repo
        $ code-context-agent viz . --port 9000
    """
    import http.server
    import socketserver
    import threading
    import webbrowser

    repo_path = path.resolve()
    agent_dir = (output_dir or repo_path / ".agent").resolve()

    if not agent_dir.exists():
        console.print(f"[red]Error:[/red] No analysis output found at {agent_dir}")
        console.print("Run [cyan]code-context-agent analyze[/cyan] first.")
        raise SystemExit(1)

    # Resolve viz directory (shipped alongside the package)
    viz_dir = Path(__file__).parent.parent.parent / "viz"
    if not viz_dir.exists():
        # Fallback: look relative to the project root
        viz_dir = Path(__file__).resolve().parent.parent.parent / "viz"
    if not viz_dir.exists():
        console.print("[red]Error:[/red] Visualization files not found.")
        raise SystemExit(1)

    # Build URL params pointing to the agent output files
    params = []
    graph_file = agent_dir / "code_graph.json"
    context_file = agent_dir / "CONTEXT.md"
    result_file = agent_dir / "analysis_result.json"

    # Check what files exist
    files_found = []
    if graph_file.exists():
        params.append("graph=/data/code_graph.json")
        files_found.append("code_graph.json")
    if context_file.exists():
        params.append("narrative=/data/CONTEXT.md")
        files_found.append("CONTEXT.md")
    if result_file.exists():
        params.append("result=/data/analysis_result.json")
        files_found.append("analysis_result.json")

    if not files_found:
        console.print(f"[yellow]Warning:[/yellow] No analysis files found in {agent_dir}")
        console.print("The visualizer will open but you'll need to load data manually.")

    query = "&".join(params)
    url = f"http://localhost:{port}/{'?' + query if query else ''}"

    # Custom handler that serves viz files and proxies /data/ to agent_dir
    class VizHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(viz_dir), **kwargs)

        def translate_path(self, path):
            """Route /data/ requests to the agent output directory."""
            if path.startswith("/data/"):
                relative = path[6:]  # strip /data/
                return str(agent_dir / relative)
            return super().translate_path(path)

        def log_message(self, format, *args):
            pass  # Suppress request logs

    console.print()
    console.print("[bold]Code Context Visualizer[/bold]")
    console.print(f"  Data: [cyan]{agent_dir}[/cyan]")
    console.print(f"  Files: {', '.join(files_found) or 'none'}")
    console.print(f"  URL: [link={url}]{url}[/link]")
    console.print()
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    if not no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    with socketserver.TCPServer(("", port), VizHandler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[dim]Server stopped[/dim]")


def _display_result(result: dict, *, debug: bool = False) -> None:
    """Display analysis result to the console.

    Args:
        result: Analysis result dictionary.
        debug: Whether debug mode is enabled.
    """
    if result["status"] == "completed":
        console.print()
        console.print("[green]Analysis completed successfully[/green]")
        console.print(f"  Output directory: [cyan]{result['output_dir']}[/cyan]")
        if result.get("context_path"):
            console.print(f"  Context file: [cyan]{result['context_path']}[/cyan]")
    elif result["status"] == "stopped":
        console.print()
        console.print(f"[yellow]Analysis stopped:[/yellow] {result.get('exceeded_limit', 'limit exceeded')}")
        console.print(f"  Turns: {result.get('turn_count', '?')}, Duration: {result.get('duration_seconds', 0):.1f}s")
        if result.get("context_path"):
            console.print(f"  Partial output: [cyan]{result['context_path']}[/cyan]")
        raise SystemExit(1)
    else:
        console.print()
        error = result.get("error") or "Unknown error (no error message captured)"
        console.print(f"[red]Analysis failed:[/red] {error}")
        if debug:
            console.print(f"[dim]Status: {result.get('status')}, Turns: {result.get('turn_count', 0)}[/dim]")
        raise SystemExit(1)


if __name__ == "__main__":
    app()
