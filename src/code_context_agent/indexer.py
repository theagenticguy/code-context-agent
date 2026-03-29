"""Deterministic indexing pipeline for building code graphs without LLM invocations.

Builds a CodeGraph by calling adapter functions directly using LSP, AST-grep,
git history, and clone detection. All external tool calls are graceful -- if a
tool is missing the step is skipped and indexing continues.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

from code_context_agent.config import DEFAULT_OUTPUT_DIR, get_settings
from code_context_agent.tools.graph.adapters import (
    ingest_astgrep_rule_pack,
    ingest_clone_results,
    ingest_git_cochanges,
    ingest_git_hotspots,
    ingest_lsp_symbols,
    ingest_test_mapping,
)
from code_context_agent.tools.graph.frameworks import detect_frameworks
from code_context_agent.tools.graph.model import CodeGraph

# Extension to LSP server kind mapping (matches LspClient._detect_language + config.lsp_servers keys)
_EXTENSION_TO_LANG: dict[str, str] = {
    ".py": "py",
    ".ts": "ts",
    ".tsx": "ts",
    ".js": "ts",
    ".jsx": "ts",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
}

# Language to ast-grep rule pack mapping
_LANG_RULE_PACKS: dict[str, list[str]] = {
    "py": ["py_business_logic", "py_code_smells"],
    "ts": ["ts_business_logic", "ts_code_smells"],
}


async def build_index(
    repo_path: Path,
    output_dir: Path | None = None,
    quiet: bool = False,
) -> CodeGraph:
    """Build a code graph deterministically without LLM invocations.

    Pipeline:
    1. File manifest via ripgrep
    2. Language detection from file extensions
    3. LSP document symbols for each file -> ingest into graph
    4. AST-grep rule packs per language -> ingest
    5. Git hotspots + co-changes -> ingest
    6. Clone detection -> ingest
    7. Save graph to output_dir

    Args:
        repo_path: Path to the repository root.
        output_dir: Where to save artifacts (default: repo_path/.code-context/).
        quiet: Suppress progress output.

    Returns:
        The built CodeGraph.
    """
    repo = repo_path.resolve()
    out = output_dir or (repo / DEFAULT_OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    graph = CodeGraph()

    # Step 1: File manifest
    files = _get_file_manifest(repo)
    if not quiet:
        logger.info(f"Indexing {len(files)} files in {repo}")

    # Step 1a: Write file manifest to disk (BM25 search checks for this)
    manifest_path = out / "files.all.txt"
    manifest_path.write_text("\n".join(files))

    # Step 2: Detect languages
    lang_files = _detect_languages(files)
    if not quiet:
        lang_summary = {lang: len(fs) for lang, fs in lang_files.items()}
        logger.info(f"Languages detected: {lang_summary}")

    # Step 3: LSP symbols (if available)
    await _ingest_lsp_symbols(graph, repo, lang_files, quiet)

    # Step 4: AST-grep rule packs
    _ingest_astgrep(graph, repo, lang_files, quiet)

    # Step 5: Git analysis
    _ingest_git(graph, repo, quiet)

    # Step 6: Clone detection
    _ingest_clones(graph, repo, quiet)

    # Step 7: Framework detection (activates dead code in frameworks.py)
    frameworks = detect_frameworks(files)
    if not quiet and frameworks:
        logger.info(f"Frameworks detected: {frameworks}")

    # Step 8: Test-to-production mapping
    _ingest_tests(graph, files, quiet)

    # Step 9: Repomix compressed signatures
    _run_repomix_signatures(repo, out, quiet)

    # Step 10: Repomix orientation
    _run_repomix_orientation(repo, out, quiet)

    # Step 11: BM25 index prebuild
    _prebuild_bm25(files, repo, quiet)

    # Step 12: Save graph
    graph_path = out / "code_graph.json"
    graph_data = graph.to_node_link_data()
    graph_path.write_text(json.dumps(graph_data, indent=2))

    graph_stats = graph.describe()
    if not quiet:
        logger.info(
            f"Index complete: {graph_stats.get('node_count', 0)} nodes, "
            f"{graph_stats.get('edge_count', 0)} edges -> {graph_path}",
        )

    # Step 13: Generate index metadata
    _write_index_metadata(graph, graph_stats, out, files, lang_files, frameworks, quiet)

    return graph


def _get_file_manifest(repo: Path) -> list[str]:
    """Get list of files in the repo using ripgrep.

    Falls back to a simple glob if rg is not available.

    Args:
        repo: Repository root path.

    Returns:
        List of file paths relative to repo root.
    """
    if shutil.which("rg") is None:
        logger.warning("ripgrep (rg) not found, falling back to Path.rglob")
        return _get_file_manifest_fallback(repo)

    try:
        result = subprocess.run(
            ["rg", "--files"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"rg --files failed: {e}, falling back to Path.rglob")

    return _get_file_manifest_fallback(repo)


def _get_file_manifest_fallback(repo: Path) -> list[str]:
    """Fallback file manifest using pathlib."""
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}
    files: list[str] = []
    for p in repo.rglob("*"):
        if p.is_file() and not any(part in skip_dirs for part in p.parts):
            try:
                files.append(str(p.relative_to(repo)))
            except ValueError:
                continue
    return files


def _detect_languages(files: list[str]) -> dict[str, list[str]]:
    """Group files by language based on file extension.

    Args:
        files: List of relative file paths.

    Returns:
        Dict mapping language key (e.g. "py", "ts") to list of file paths.
    """
    lang_files: dict[str, list[str]] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = _EXTENSION_TO_LANG.get(ext)
        if lang:
            lang_files.setdefault(lang, []).append(f)
    return lang_files


async def _ingest_lsp_symbols(  # noqa: C901
    graph: CodeGraph,
    repo: Path,
    lang_files: dict[str, list[str]],
    quiet: bool,
) -> None:
    """Ingest LSP document symbols into the graph.

    For each language with a configured LSP server, starts a session and
    gets document symbols for each file. Failures are handled gracefully.
    """
    from code_context_agent.tools.lsp.session import LspSessionManager

    settings = get_settings()
    manager = LspSessionManager()
    workspace = str(repo)

    for lang, files in lang_files.items():
        if lang not in settings.lsp_servers:
            continue

        try:
            client = await manager.get_or_create(lang, workspace, startup_timeout=15.0)
        except (RuntimeError, ValueError, OSError, TimeoutError) as e:
            logger.warning(f"LSP startup failed for {lang}: {e} -- skipping LSP symbols")
            continue

        if not quiet:
            logger.info(f"LSP indexing {len(files)} {lang} files")

        for file_rel in files:
            file_abs = str(repo / file_rel)
            try:
                symbols = await client.document_symbols(file_abs)
                if symbols:
                    symbols_result: dict[str, Any] = {"status": "success", "symbols": symbols}
                    nodes, edges = ingest_lsp_symbols(symbols_result, file_rel)
                    for node in nodes:
                        graph.add_node(node)
                    for edge in edges:
                        graph.add_edge(edge)
            except (OSError, TimeoutError, RuntimeError, FileNotFoundError) as e:
                logger.debug(f"LSP symbols failed for {file_rel}: {e}")
                continue

    try:
        await manager.shutdown_all()
    except (OSError, RuntimeError) as e:
        logger.debug(f"LSP shutdown error: {e}")


def _ingest_astgrep(  # noqa: C901
    graph: CodeGraph,
    repo: Path,
    lang_files: dict[str, list[str]],
    quiet: bool,
) -> None:
    """Ingest AST-grep rule pack matches into the graph."""
    if shutil.which("ast-grep") is None:
        logger.warning("ast-grep not found -- skipping AST analysis")
        return

    rules_dir = Path(__file__).parent / "rules"

    for lang, _files in lang_files.items():
        rule_packs = _LANG_RULE_PACKS.get(lang, [])
        for pack_name in rule_packs:
            rule_file = rules_dir / f"{pack_name}.yml"
            if not rule_file.exists():
                continue

            try:
                result = subprocess.run(
                    ["ast-grep", "scan", "--config", str(rule_file), "--json=stream", str(repo)],
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
                logger.warning(f"ast-grep rule pack {pack_name} failed: {e}")
                continue

            # Parse streaming JSON and build result dict matching adapter format
            matches_by_rule: dict[str, list[dict[str, Any]]] = {}
            total_count = 0
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rule_id = data.get("ruleId", "unknown")
                        match = {
                            "file": data.get("file", ""),
                            "range": data.get("range", {}),
                            "text": data.get("text", ""),
                            "message": data.get("message", ""),
                        }
                        matches_by_rule.setdefault(rule_id, []).append(match)
                        total_count += 1
                    except json.JSONDecodeError:
                        continue

            if matches_by_rule:
                pack_result = {
                    "status": "success",
                    "rule_pack": pack_name,
                    "matches_by_rule": matches_by_rule,
                    "total_count": total_count,
                }
                nodes = ingest_astgrep_rule_pack(pack_result)
                for node in nodes:
                    graph.add_node(node)

                if not quiet:
                    logger.info(f"ast-grep {pack_name}: {total_count} matches in {len(matches_by_rule)} rules")


def _ingest_git(graph: CodeGraph, repo: Path, quiet: bool) -> None:  # noqa: C901
    """Ingest git hotspots and co-change data into the graph."""
    # Hotspots
    try:
        result = subprocess.run(
            ["git", "log", "-n200", "--pretty=format:", "--name-only"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Git hotspot analysis failed: {e}")
        return

    if result.returncode != 0:
        logger.warning(f"Git hotspot analysis failed: {result.stderr[:200]}")
        return

    file_counter: Counter[str] = Counter()
    commit_count = 0
    in_commit = False

    for raw_line in result.stdout.strip().splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if in_commit:
                commit_count += 1
            in_commit = False
            continue
        in_commit = True
        file_counter[stripped] += 1
    if in_commit:
        commit_count += 1

    if commit_count == 0:
        return

    hotspots = [
        {"path": path, "commits": count, "percentage": round(100 * count / commit_count, 1)}
        for path, count in file_counter.most_common(30)
    ]

    hotspots_result: dict[str, Any] = {
        "status": "success",
        "hotspots": hotspots,
        "total_commits_analyzed": commit_count,
    }
    nodes = ingest_git_hotspots(hotspots_result)
    for node in nodes:
        graph.add_node(node)

    if not quiet:
        logger.info(f"Git hotspots: {len(hotspots)} files from {commit_count} commits")

    # Co-changes for top hotspot files
    top_files = [str(h["path"]) for h in hotspots[:10]]
    for file_path in top_files:
        cochange_result = _get_git_cochanges(repo, file_path)
        if cochange_result:
            edges = ingest_git_cochanges(cochange_result)
            for edge in edges:
                graph.add_edge(edge)


def _get_git_cochanges(repo: Path, file_path: str) -> dict[str, Any] | None:
    """Get co-change data for a single file."""
    try:
        commits_result = subprocess.run(
            ["git", "log", "-n100", "--pretty=format:%H", "--", file_path],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return None

    if commits_result.returncode != 0:
        return None

    commit_hashes = [h.strip() for h in commits_result.stdout.strip().splitlines() if h.strip()]
    if not commit_hashes:
        return None

    cochange_counter: Counter[str] = Counter()
    total_commits = len(commit_hashes)

    for commit_hash in commit_hashes:
        try:
            files_result = subprocess.run(
                ["git", "show", "--pretty=format:", "--name-only", commit_hash],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if files_result.returncode == 0:
                changed = [f.strip() for f in files_result.stdout.strip().splitlines() if f.strip()]
                other = [f for f in changed if f != file_path]
                cochange_counter.update(other)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            continue

    if not cochange_counter:
        return None

    cochanged_files = [
        {"path": path, "count": count, "percentage": round(100 * count / total_commits, 1)}
        for path, count in cochange_counter.most_common(50)
    ]

    return {
        "status": "success",
        "file_path": file_path,
        "total_commits": total_commits,
        "cochanged_files": cochanged_files,
    }


def _ingest_clones(graph: CodeGraph, repo: Path, quiet: bool) -> None:
    """Ingest clone detection results into the graph."""
    if shutil.which("npx") is None:
        logger.warning("npx not found -- skipping clone detection")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [
                    "npx",
                    "-y",
                    "jscpd@4",
                    "--reporters",
                    "json",
                    "--output",
                    tmpdir,
                    "--format",
                    "python,typescript,javascript",
                    "--gitignore",
                    "--min-lines",
                    "10",
                    "--max-size",
                    "50kb",
                    "--silent",
                    str(repo),
                ],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Clone detection failed: {e}")
            return

        # jscpd writes jscpd-report.json to the output directory
        report_path = Path(tmpdir) / "jscpd-report.json"
        if not report_path.exists():
            logger.debug(f"jscpd report not found (exit code {result.returncode})")
            return

        clones: list[dict[str, Any]] = []
        try:
            data = json.loads(report_path.read_text())
            duplicates = data.get("duplicates", [])
            for dup in duplicates:
                first = dup.get("firstFile", {})
                second = dup.get("secondFile", {})
                clones.append(
                    {
                        "first_file": first.get("name", ""),
                        "second_file": second.get("name", ""),
                        "first_start": first.get("startLoc", {}).get("line", 0),
                        "first_end": first.get("endLoc", {}).get("line", 0),
                        "second_start": second.get("startLoc", {}).get("line", 0),
                        "second_end": second.get("endLoc", {}).get("line", 0),
                        "lines": dup.get("lines", 0),
                        "tokens": dup.get("tokens", 0),
                        "fragment": dup.get("fragment", "")[:200],
                    },
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.debug("Could not parse jscpd output")
            return

    if clones:
        clone_result: dict[str, Any] = {"status": "success", "clones": clones}
        edges = ingest_clone_results(clone_result)
        for edge in edges:
            graph.add_edge(edge)

        if not quiet:
            logger.info(f"Clone detection: {len(clones)} duplicate blocks found")


# --------------------------------------------------------------------------- #
# New deterministic steps (7-13)
# --------------------------------------------------------------------------- #

_TEST_PATTERNS = {"test_", "_test.", ".test.", ".spec.", "__tests__"}


def _ingest_tests(graph: CodeGraph, files: list[str], quiet: bool) -> None:
    """Ingest test-to-production mapping using filename conventions."""
    test_files = [f for f in files if any(p in f.lower() for p in _TEST_PATTERNS)]
    prod_files = [f for f in files if f not in set(test_files)]

    if not test_files:
        return

    edges = ingest_test_mapping(test_files, prod_files)
    for edge in edges:
        graph.add_edge(edge)

    if not quiet:
        logger.info(f"Test mapping: {len(edges)} test→production edges from {len(test_files)} test files")


def _run_repomix_signatures(repo: Path, out: Path, quiet: bool) -> None:
    """Generate compressed signatures via repomix (tree-sitter body stripping)."""
    if shutil.which("repomix") is None:
        logger.debug("repomix not found -- skipping signatures")
        return

    sig_path = out / "CONTEXT.signatures.md"
    try:
        subprocess.run(
            [
                "repomix",
                "--compress",
                "--remove-comments",
                "--remove-empty-lines",
                "--style",
                "markdown",
                "-o",
                str(sig_path),
                str(repo),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if not quiet and sig_path.exists():
            size_kb = sig_path.stat().st_size / 1024
            logger.info(f"Repomix signatures: {size_kb:.0f}KB -> {sig_path}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Repomix signatures failed: {e}")


def _run_repomix_orientation(repo: Path, out: Path, quiet: bool) -> None:
    """Generate token-aware orientation overview via repomix."""
    if shutil.which("repomix") is None:
        logger.debug("repomix not found -- skipping orientation")
        return

    orient_path = out / "CONTEXT.orientation.md"
    try:
        subprocess.run(
            [
                "repomix",
                "--no-files",
                "--style",
                "markdown",
                "--token-count-tree",
                "300",
                "-o",
                str(orient_path),
                str(repo),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if not quiet and orient_path.exists():
            size_kb = orient_path.stat().st_size / 1024
            logger.info(f"Repomix orientation: {size_kb:.0f}KB -> {orient_path}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Repomix orientation failed: {e}")


def _prebuild_bm25(files: list[str], repo: Path, quiet: bool) -> None:
    """Pre-build BM25 search index so first search has zero latency."""
    try:
        from code_context_agent.tools.search.bm25 import BM25Index
        from code_context_agent.tools.search.tools import _indexes

        index = BM25Index.from_files(files, repo)
        _indexes[str(repo)] = index
        if not quiet:
            logger.info(f"BM25 index: {len(files)} files indexed")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"BM25 prebuild failed: {e}")


def _write_index_metadata(
    graph: CodeGraph,
    graph_stats: dict[str, Any],
    out: Path,
    files: list[str],
    lang_files: dict[str, list[str]],
    frameworks: list[str],
    quiet: bool,
) -> None:
    """Write index metadata JSON for coordinator consumption."""
    from datetime import UTC, datetime

    from code_context_agent.tools.graph.analysis import CodeAnalyzer

    analyzer = CodeAnalyzer(graph)

    try:
        entry_points = analyzer.find_entry_points()[:10]
    except Exception:  # noqa: BLE001
        entry_points = []

    try:
        hotspots = analyzer.find_hotspots(10)
    except Exception:  # noqa: BLE001
        hotspots = []

    from code_context_agent.models.index import IndexMetadata

    metadata = IndexMetadata(
        file_count=len(files),
        languages={lang: len(fs) for lang, fs in lang_files.items()},
        frameworks=frameworks,
        graph_stats=graph_stats,
        top_entry_points=entry_points,
        top_hotspots=hotspots,
        indexed_at=datetime.now(tz=UTC).isoformat(),
        has_signatures=(out / "CONTEXT.signatures.md").exists(),
        has_orientation=(out / "CONTEXT.orientation.md").exists(),
    )

    metadata_path = out / "index_metadata.json"
    metadata_path.write_text(metadata.model_dump_json(indent=2))

    if not quiet:
        logger.info(f"Index metadata: {metadata_path}")
