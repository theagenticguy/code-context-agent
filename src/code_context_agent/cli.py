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
from code_context_agent.config import DEFAULT_OUTPUT_DIR, Settings, get_settings
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
def analyze(  # noqa: C901, PLR0912
    path: Annotated[
        Path,
        Parameter(help="Path to the repository to analyze."),
    ] = Path(),
    *,
    output_dir: Annotated[
        Path | None,
        Parameter(help="Output directory for context files. Defaults to <repo>/.code-context"),
    ] = None,
    focus: Annotated[
        str,
        Parameter(help="Focus area for analysis (e.g., 'authentication', 'API endpoints', 'database layer')."),
    ] = "",
    issue: Annotated[
        str,
        Parameter(help="Issue reference for focused analysis (e.g., 'gh:1694', 'gh:owner/repo#1694')."),
    ] = "",
    output_format: Annotated[
        Literal["rich", "json"],
        Parameter(help="Output format: rich (default TUI), json (AnalysisResult JSON to stdout)."),
    ] = "rich",
    since: Annotated[
        str,
        Parameter(
            help="Git ref for incremental analysis (e.g., 'HEAD~5', 'main', 'abc123'). "
            "Only re-analyzes files changed since this ref.",
        ),
    ] = "",
    full: Annotated[
        bool,
        Parameter(help="Run exhaustive analysis with no size limits and fail-fast error handling."),
    ] = False,
    quiet: Annotated[
        bool,
        Parameter(help="Suppress all output except errors on stderr. No TUI, no JSON."),
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
        .code-context/CONTEXT.md - The narrated context bundle
        .code-context/CONTEXT.orientation.md - Token distribution tree
        .code-context/CONTEXT.bundle.md - Curated source code pack

    Example:
        $ code-context-agent analyze /path/to/repo
        $ code-context-agent analyze . --focus "authentication"
        $ code-context-agent analyze . --output-dir ./output
        $ code-context-agent analyze . --issue "gh:1694"
    """
    import asyncio
    import sys

    from loguru import logger

    from code_context_agent.agent import run_analysis
    from code_context_agent.utils import setup_logger

    # Configure logging: suppress loguru in normal mode (Rich Live conflict),
    # enable full logging in debug mode (which uses QuietConsumer instead)
    if debug:
        setup_logger(level="DEBUG")
        if not quiet:
            console.print("[dim]Debug logging enabled (live display disabled)[/dim]")
    else:
        # Remove default loguru handler to prevent stderr writes that break Rich Live
        logger.remove()
        setup_logger(level="WARNING")

    repo_path = path.resolve()

    if not repo_path.exists():
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        raise SystemExit(1)

    if not repo_path.is_dir():
        print(f"Error: Path is not a directory: {repo_path}", file=sys.stderr)
        raise SystemExit(1)

    # Validate flag combinations
    _validate_flags(full=full, since=since)

    # Derive analysis mode
    mode = _derive_mode(full=full, focus=focus, since=since)

    # Auto-preflight in full mode
    if full and not quiet:
        preflight = _preflight_check()
        missing = [name for name, info in preflight.items() if not info["available"]]
        if missing:
            console.print(f"[yellow]Warning:[/yellow] Missing tools: {', '.join(missing)}")
            console.print("  Full mode works best with all tools installed.")

    # Show analysis configuration
    if not quiet:
        console.print()
        console.print("[bold]Code Context Analysis[/bold]")
        console.print(f"  Repository: [cyan]{repo_path}[/cyan]")
        if focus:
            console.print(f"  Focus: [magenta]{focus}[/magenta]")
        if full:
            console.print("  Mode: [bold magenta]FULL (exhaustive)[/bold magenta]")
        console.print()

    # In debug mode or JSON mode, use quiet consumer (log output replaces Live display)
    use_quiet = quiet or debug or (output_format == "json")

    # Fetch issue context if provided (deterministic, not model-invoked)
    issue_context = _fetch_issue_context(issue, quiet=use_quiet) if issue else None

    # Build incremental analysis context if --since provided
    since_context = None
    if since:
        effective_output = output_dir or repo_path / DEFAULT_OUTPUT_DIR
        since_context = _build_since_context(repo_path, since, effective_output)
    if since_context and not use_quiet:
        console.print(f"  Incremental: [magenta]since {since}[/magenta]")

    # Run the analysis
    result = asyncio.run(
        run_analysis(
            repo_path=repo_path,
            output_dir=output_dir,
            focus=focus or None,
            quiet=use_quiet,
            issue_context=issue_context,
            since_context=since_context,
            mode=mode,
        ),
    )

    if output_format == "json":
        _display_result_json(result)
    else:
        _display_result(result, debug=debug, quiet=quiet)


@app.command
def viz(  # noqa: C901, PLR0915
    path: Annotated[
        Path,
        Parameter(help="Path to the repository (must contain .code-context/ output)."),
    ] = Path(),
    *,
    output_dir: Annotated[
        Path | None,
        Parameter(help="Output directory containing analysis results. Defaults to <path>/.code-context"),
    ] = None,
    port: Annotated[
        int,
        Parameter(help="Port for the local HTTP server."),
    ] = 8765,
    no_open: Annotated[
        bool,
        Parameter(help="Don't auto-open the browser."),
    ] = False,
    legacy_viz: Annotated[
        bool,
        Parameter(help="Use the legacy single-page D3.js visualizer instead of the default multi-view UI."),
    ] = False,
) -> None:
    """Launch an interactive visualization of analysis results.

    Serves a local web UI with 10 views: dashboard, graph, modules, hotspots,
    dependencies, narrative, bundles, insights, signatures, and landing.

    Requires a prior `analyze` or `index` run to generate .code-context/ output files.

    Example:
        $ code-context-agent viz /path/to/repo
        $ code-context-agent viz . --port 9000
        $ code-context-agent viz . --legacy-viz  # old single-page visualizer
    """
    import http.server
    import socketserver
    import threading
    import webbrowser

    repo_path = path.resolve()
    agent_dir = (output_dir or repo_path / DEFAULT_OUTPUT_DIR).resolve()

    if not agent_dir.exists():
        console.print(f"[red]Error:[/red] No analysis output found at {agent_dir}")
        console.print("Run [cyan]code-context-agent analyze[/cyan] first.")
        raise SystemExit(1)

    # Resolve viz directory — ui-next is the default, legacy is opt-in
    if legacy_viz:
        viz_dir = Path(__file__).parent / "viz"
    else:
        # ui-next lives at the repo root (sibling to src/)
        viz_dir = Path(__file__).parent.parent.parent / "ui-next"
        if not viz_dir.exists():
            # Fallback: check relative to CWD
            viz_dir = repo_path / "ui-next"
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

        def do_GET(self):
            """Handle GET requests with API endpoints and file serving."""
            if self.path == "/api/graph" or self.path.startswith("/api/graph?"):
                self._serve_json_file("code_graph.json")
                return
            if self.path == "/api/stats" or self.path.startswith("/api/stats?"):
                self._serve_graph_stats()
                return
            super().do_GET()

        def translate_path(self, path):
            """Route /data/ requests to the agent output directory."""
            if path.startswith("/data/"):
                relative = path[6:]  # strip /data/
                resolved = (agent_dir / relative).resolve()
                # Prevent path traversal outside agent_dir
                if not str(resolved).startswith(str(agent_dir)):
                    return str(agent_dir / "404")
                return str(resolved)
            return super().translate_path(path)

        def _serve_json_file(self, filename: str) -> None:
            """Serve a JSON file from agent_dir."""
            filepath = agent_dir / filename
            if not filepath.exists():
                self.send_error(404, f"{filename} not found")
                return
            data = filepath.read_text(encoding="utf-8")
            encoded = data.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(encoded)

        def _serve_graph_stats(self) -> None:
            """Load graph and serve describe() as JSON."""
            import json

            filepath = agent_dir / "code_graph.json"
            if not filepath.exists():
                self.send_error(404, "code_graph.json not found")
                return
            try:
                raw = json.loads(filepath.read_text(encoding="utf-8"))
                from code_context_agent.tools.graph.model import CodeGraph

                graph = CodeGraph.from_node_link_data(raw)
                stats = graph.describe()
                body = json.dumps(stats, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except (KeyError, ValueError, OSError) as exc:
                self.send_error(500, str(exc))

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

    with socketserver.TCPServer(("127.0.0.1", port), VizHandler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[dim]Server stopped[/dim]")


@app.command
def index(
    path: Annotated[
        Path,
        Parameter(help="Path to the repository to index."),
    ] = Path(),
    *,
    output_dir: Annotated[
        Path | None,
        Parameter(help="Output directory for the code graph. Defaults to <repo>/.code-context"),
    ] = None,
    quiet: Annotated[
        bool,
        Parameter(help="Suppress all output except errors."),
    ] = False,
) -> None:
    """Build a code graph deterministically without LLM calls.

    Faster and cheaper than full analysis. Uses LSP, AST-grep, and git
    to build a structural code graph that can be queried via MCP tools.

    Example:
        $ code-context-agent index /path/to/repo
        $ code-context-agent index . --output-dir ./output
        $ code-context-agent index . --quiet
    """
    import asyncio
    import sys

    from code_context_agent.indexer import build_index

    repo_path = path.resolve()

    if not repo_path.exists():
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        raise SystemExit(1)

    if not repo_path.is_dir():
        print(f"Error: Path is not a directory: {repo_path}", file=sys.stderr)
        raise SystemExit(1)

    asyncio.run(build_index(repo_path, output_dir, quiet))


@app.command
def serve(
    *,
    transport: Annotated[
        Literal["stdio", "http", "sse"],
        Parameter(help="MCP transport: stdio (default, for Claude Desktop/CLI), http (networked), sse (legacy)."),
    ] = "stdio",
    host: Annotated[
        str,
        Parameter(help="Host to bind for http/sse transport."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        Parameter(help="Port for http/sse transport."),
    ] = 8000,
) -> None:
    """Start the MCP server exposing code-context-agent's analysis capabilities.

    Exposes the core differentiators — full analysis pipeline, code graph
    algorithms, and progressive exploration — via the Model Context Protocol.

    Transports:
        stdio: For Claude Desktop, Claude Code, and local MCP clients (default)
        http:  For networked/multi-client access (Streamable HTTP)
        sse:   For legacy MCP clients only

    Example:
        $ code-context-agent serve                          # stdio for Claude Desktop
        $ code-context-agent serve --transport http         # HTTP on localhost:8000
        $ code-context-agent serve --transport http --port 9000
    """
    from code_context_agent.mcp import mcp as mcp_server

    if transport == "stdio":
        console.print("[dim]Starting MCP server (stdio transport)...[/dim]")
    else:
        console.print(f"[dim]Starting MCP server ({transport} transport on {host}:{port})...[/dim]")

    mcp_server.run(transport=transport, host=host, port=port)


@app.command
def check() -> None:
    """Check availability of external tool dependencies.

    Verifies that ripgrep, ast-grep, repomix, and npx are installed
    and accessible. Useful for diagnosing setup issues before running
    analysis.

    Example:
        $ code-context-agent check
    """
    preflight = _preflight_check()
    all_ok = True
    for name, info in preflight.items():
        if info["available"]:
            console.print(f"  [green]\u2713[/green] {name}")
        else:
            console.print(f"  [red]\u2717[/red] {name} \u2014 install via {info['package']}")
            all_ok = False
    if all_ok:
        console.print("\n[green]All tools available.[/green]")
    else:
        console.print("\n[yellow]Some tools are missing. Analysis may be limited.[/yellow]")
        raise SystemExit(1)


def _preflight_check() -> dict[str, dict[str, bool | str]]:
    """Check availability of external tool dependencies.

    Returns:
        Dict mapping tool name to status info.
    """
    import shutil

    tools = {
        "ripgrep": {"cmd": "rg", "package": "ripgrep"},
        "ast-grep": {"cmd": "ast-grep", "package": "ast-grep (npm)"},
        "repomix": {"cmd": "repomix", "package": "repomix (npm)"},
        "npx": {"cmd": "npx", "package": "Node.js"},
    }

    result: dict[str, dict[str, bool | str]] = {}
    for name, info in tools.items():
        available = shutil.which(info["cmd"]) is not None
        result[name] = {"available": available, "package": info["package"]}

    return result


def _validate_flags(*, full: bool = False, since: str = "") -> None:
    """Validate mutually exclusive flag combinations.

    Raises:
        SystemExit: If invalid flag combinations are detected.
    """
    if full and since:
        console.print("[red]Error:[/red] --full and --since cannot be combined.")
        console.print("  --full runs exhaustive analysis on the entire repo.")
        console.print("  --since runs incremental analysis on changed files only.")
        raise SystemExit(1)


def _derive_mode(*, full: bool = False, focus: str = "", since: str = "") -> str:
    """Derive the analysis mode string from CLI flags.

    Returns:
        Mode string: "standard", "full", "focus", "incremental", or "full+focus".
    """
    if full and focus:
        return "full+focus"
    if full:
        return "full"
    if focus:
        return "focus"
    if since:
        return "incremental"
    return "standard"


def _fetch_issue_context(issue: str, *, quiet: bool = False) -> str | None:
    """Fetch and render issue context from a provider reference.

    Args:
        issue: Issue reference string (e.g., 'gh:1694', 'gh:owner/repo#1694').
        quiet: Suppress non-error output.

    Returns:
        Rendered issue context string, or None if fetching failed.
    """
    from code_context_agent.issues import render_issue_context
    from code_context_agent.issues.github import GitHubIssueProvider, parse_issue_ref

    try:
        provider_name, issue_ref = parse_issue_ref(issue)
        if provider_name == "gh":
            provider = GitHubIssueProvider()
            fetched_issue = provider.fetch(issue_ref)
            if not quiet:
                console.print(f"  Issue: [magenta]{fetched_issue.title}[/magenta]")
            return render_issue_context(fetched_issue)
        if not quiet:
            console.print(f"[yellow]Warning:[/yellow] Unsupported issue provider: {provider_name}")
    except RuntimeError as e:
        if not quiet:
            console.print(f"[yellow]Warning:[/yellow] Could not fetch issue: {e}")
    return None


def _display_result(result: dict, *, debug: bool = False, quiet: bool = False) -> None:
    """Display analysis result to the console.

    In quiet mode, only errors are printed to stderr with no formatting.

    Args:
        result: Analysis result dictionary.
        debug: Whether debug mode is enabled.
        quiet: Whether quiet mode is enabled.
    """
    import sys

    if result["status"] == "completed":
        if not quiet:
            console.print()
            console.print("[green]Analysis completed successfully[/green]")
            console.print(f"  Output directory: [cyan]{result['output_dir']}[/cyan]")
            if result.get("context_path"):
                console.print(f"  Context file: [cyan]{result['context_path']}[/cyan]")
    elif result["status"] == "stopped":
        if quiet:
            print(
                f"Error: Analysis stopped: {result.get('exceeded_limit', 'limit exceeded')}",
                file=sys.stderr,
            )
        else:
            console.print()
            console.print(f"[yellow]Analysis stopped:[/yellow] {result.get('exceeded_limit', 'limit exceeded')}")
            console.print(
                f"  Turns: {result.get('turn_count', '?')}, Duration: {result.get('duration_seconds', 0):.1f}s",
            )
            if result.get("context_path"):
                console.print(f"  Partial output: [cyan]{result['context_path']}[/cyan]")
        raise SystemExit(1)
    else:
        error = result.get("error") or "Unknown error (no error message captured)"
        if quiet:
            print(f"Error: {error}", file=sys.stderr)
        else:
            console.print()
            console.print(f"[red]Analysis failed:[/red] {error}")
            if debug:
                console.print(f"[dim]Status: {result.get('status')}, Turns: {result.get('turn_count', 0)}[/dim]")
        raise SystemExit(1)


def _build_since_context(repo_path: Path, since: str, output_dir: Path) -> str | None:
    """Build incremental analysis context from git diff.

    Args:
        repo_path: Repository path.
        since: Git ref to diff against.
        output_dir: Output directory to check for existing artifacts.

    Returns:
        XML-wrapped since context string, or None if git diff fails or is empty.
    """
    import html as _html
    import subprocess

    try:
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", f"{since}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None

    changed_files = [f.strip() for f in diff_result.stdout.strip().splitlines() if f.strip()]
    if not changed_files:
        return None

    has_existing_graph = (output_dir / "code_graph.json").exists()
    has_existing_context = (output_dir / "CONTEXT.md").exists()
    safe_since = _html.escape(since)
    file_list = "\n".join(f"- {f}" for f in changed_files)

    return (
        f"<since_context>\n"
        f"<ref>{safe_since}</ref>\n"
        f"<changed_file_count>{len(changed_files)}</changed_file_count>\n"
        f"<changed_files>\n{file_list}\n</changed_files>\n"
        f"<has_existing_graph>{has_existing_graph}</has_existing_graph>\n"
        f"<has_existing_context>{has_existing_context}</has_existing_context>\n"
        f"<output_dir>{output_dir}</output_dir>\n"
        f"</since_context>"
    )


def _display_result_json(result: dict) -> None:
    """Write analysis result as JSON to stdout.

    On success, reads the analysis_result.json written by the agent.
    Falls back to the run metadata dict if the file doesn't exist.
    On error/stopped, writes JSON to stderr and exits with code 1.

    Args:
        result: Analysis run result dictionary.
    """
    import json
    import sys

    if result["status"] == "completed":
        analysis_result_path = Path(result["output_dir"]) / "analysis_result.json"
        if analysis_result_path.exists():
            sys.stdout.write(analysis_result_path.read_text())
            sys.stdout.write("\n")
        else:
            print(json.dumps(result, indent=2))
        return

    # Error or stopped
    error_payload = {
        "status": result["status"],
        "error": result.get("error"),
        "exceeded_limit": result.get("exceeded_limit"),
    }
    print(json.dumps(error_payload, indent=2), file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    app()
