"""Deterministic indexing pipeline for building code graphs without LLM invocations.

Builds a CodeGraph by calling adapter functions directly using LSP, AST-grep,
git history, and clone detection. All external tool calls are graceful -- if a
tool is missing the step is skipped and indexing continues.
"""

from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

from code_context_agent.config import DEFAULT_OUTPUT_DIR, get_settings
from code_context_agent.tools.graph.adapters import (
    create_category_edges,
    create_file_bridge_nodes,
    ingest_astgrep_rule_pack,
    ingest_clone_results,
    ingest_git_cochanges,
    ingest_git_hotspots,
    ingest_lsp_symbols,
    ingest_static_imports,
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

    # Step 3a: File bridge nodes (connect file-path namespace to symbol namespace)
    _create_file_bridge(graph, quiet)

    # Step 4: AST-grep rule packs
    _ingest_astgrep(graph, repo, lang_files, quiet)

    # Step 4a: Static import parsing (FILE→FILE IMPORTS edges)
    _ingest_static_imports(graph, repo, files, lang_files, quiet)

    # Step 4b: Category-based semantic edges (SIMILAR_TO between same-category PATTERN_MATCH nodes)
    _ingest_category_edges(graph, quiet)

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

    # Step 11a: Semantic embedding enrichment (optional, adds SIMILAR_TO edges)
    _run_semantic_enrichment(graph, repo, out, files, quiet)

    # Step 12: Save graph
    graph_path = out / "code_graph.json"
    graph_data = graph.to_node_link_data()
    graph_path.write_text(json.dumps(graph_data, indent=2))

    _write_parquet_artifacts(graph_data, out, quiet)

    graph_stats = graph.describe()
    if not quiet:
        logger.info(
            f"Index complete: {graph_stats.get('node_count', 0)} nodes, "
            f"{graph_stats.get('edge_count', 0)} edges -> {graph_path}",
        )

    # Step 13: Generate index metadata
    _write_index_metadata(graph, graph_stats, out, files, lang_files, frameworks, quiet)

    # Step 14-15: Semgrep
    _run_semgrep_auto(repo, out, quiet)
    _run_semgrep_owasp(repo, out, quiet)

    # Step 16: Type checker
    _run_typecheck(repo, out, lang_files, quiet)

    # Step 17: Linter
    _run_lint(repo, out, quiet)

    # Step 18: Complexity
    _run_complexity(repo, out, lang_files, quiet)

    # Step 19-20: Dead code
    _run_dead_code_py(repo, out, lang_files, quiet)
    _run_dead_code_ts(repo, out, lang_files, quiet)

    # Step 21: Dependencies
    _run_deps(repo, out, lang_files, quiet)

    # Final: Heuristic summary
    _generate_heuristic_summary(graph, graph_stats, files, lang_files, frameworks, out, repo, quiet)

    return graph


def _flatten_records(
    raw_items: list[dict[str, Any]],
    core_fields: set[str],
    promoted_fields: set[str],
    extra_skip: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten graph dicts into records with core, promoted, and catch-all metadata columns.

    Args:
        raw_items: Raw node or edge dicts from graph export.
        core_fields: Fields always included (extracted via ``.get``).
        promoted_fields: Optional fields included only when present.
        extra_skip: Additional keys to exclude from the metadata catch-all.

    Returns:
        List of flat dicts suitable for ``pl.DataFrame``.
    """
    skip = core_fields | promoted_fields | (extra_skip or set())
    records = []
    for item in raw_items:
        record = {f: item.get(f) for f in core_fields}
        for f in promoted_fields:
            if f in item:
                record[f] = item[f]
        extra = {k: v for k, v in item.items() if k not in skip}
        record["metadata_json"] = json.dumps(extra) if extra else None
        records.append(record)
    return records


def _write_parquet_artifacts(graph_data: dict[str, Any], out: Path, quiet: bool) -> None:
    """Write nodes and edges as parquet files for fast dashboard loading."""
    try:
        import polars as pl  # ty: ignore[unresolved-import]
    except ImportError:
        if not quiet:
            logger.debug("polars not installed, skipping parquet export")
        return

    nodes_raw = graph_data.get("nodes", [])
    if not nodes_raw:
        return

    node_records = _flatten_records(
        nodes_raw,
        core_fields={"id", "name", "node_type", "file_path", "line_start", "line_end"},
        promoted_fields={"lsp_kind", "category", "rule_id", "commits", "churn_percentage", "source"},
    )
    nodes_df = pl.DataFrame(node_records)
    nodes_df.write_parquet(out / "nodes.parquet", compression="zstd")

    edges_raw = graph_data.get("links", graph_data.get("edges", []))
    edge_records = _flatten_records(
        edges_raw,
        core_fields={"source", "target", "edge_type", "weight", "confidence"},
        promoted_fields={"count", "percentage", "duplicated_lines", "import_statement"},
        extra_skip={"key"},
    )
    edges_df = pl.DataFrame(edge_records)
    edges_df.write_parquet(out / "edges.parquet", compression="zstd")

    if not quiet:
        logger.info(f"Parquet artifacts: {len(nodes_raw)} nodes, {len(edges_raw)} edges")


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


def _create_file_bridge(graph: CodeGraph, quiet: bool) -> None:
    """Create FILE bridge nodes linking file-path IDs to symbol-level IDs.

    Git co-change, test mapping, and clone detection edges use raw file paths
    as node IDs, while LSP symbols use ``file_path:symbol_name:line``.  This
    step creates a FILE node per source file and CONTAINS edges to every child
    symbol, bridging the two namespaces so the graph is fully connected.
    """
    nodes, edges = create_file_bridge_nodes(graph)
    for node in nodes:
        graph.add_node(node)
    for edge in edges:
        graph.add_edge(edge)

    if not quiet:
        logger.info(f"File bridge: {len(nodes)} FILE nodes, {len(edges)} CONTAINS edges")


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


def _ingest_category_edges(graph: CodeGraph, quiet: bool) -> None:
    """Create SIMILAR_TO edges between PATTERN_MATCH nodes sharing the same category."""
    edges = create_category_edges(graph)
    for edge in edges:
        graph.add_edge(edge)

    if not quiet and edges:
        logger.info(f"Category edges: {len(edges)} SIMILAR_TO edges")


def _ingest_static_imports(  # noqa: C901
    graph: CodeGraph,
    repo: Path,
    files: list[str],
    lang_files: dict[str, list[str]],
    quiet: bool,
) -> None:
    """Parse import statements via ripgrep and create FILE→FILE IMPORTS edges.

    Uses ``rg`` to find import/require lines, then resolves each imported module
    to a file path in the repository. Only creates edges where both the source
    and target FILE nodes exist (or exist in the file list).
    """
    if shutil.which("rg") is None:
        logger.debug("ripgrep not found -- skipping static import parsing")
        return

    all_files = set(files)
    import_map: dict[str, list[dict[str, str]]] = {}

    # --- Python imports ---
    if "py" in lang_files:
        py_imports = _rg_python_imports(repo)
        for file_path, raw_imports in py_imports.items():
            for stmt, module in raw_imports:
                import_map.setdefault(file_path, []).append({"module": module, "statement": stmt})

    # --- JS/TS imports ---
    if "ts" in lang_files:
        js_imports = _rg_js_imports(repo)
        for file_path, raw_imports in js_imports.items():
            for stmt, module in raw_imports:
                import_map.setdefault(file_path, []).append({"module": module, "statement": stmt})

    if not import_map:
        return

    edges = ingest_static_imports(import_map, all_files)
    for edge in edges:
        graph.add_edge(edge)

    if not quiet:
        logger.info(f"Static imports: {len(edges)} IMPORTS edges from {len(import_map)} files")


# Python import regex patterns
_PY_FROM_IMPORT = re.compile(r"^from\s+([\w.]+)\s+import\s+")
_PY_IMPORT = re.compile(r"^import\s+([\w.]+)")
_PY_FROM_RELATIVE = re.compile(r"^from\s+(\.+[\w.]*)\s+import\s+")

# JS/TS import regex patterns
_JS_IMPORT_FROM = re.compile(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""")
_JS_REQUIRE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")


def _parse_python_import_line(line_text: str) -> str | None:
    """Extract the module name from a single Python import line.

    Args:
        line_text: A stripped line of Python source code.

    Returns:
        The dotted module name, or ``None`` if no import pattern matched.
    """
    for pattern in (_PY_FROM_RELATIVE, _PY_FROM_IMPORT, _PY_IMPORT):
        m = pattern.match(line_text)
        if m:
            return m.group(1)
    return None


def _rg_python_imports(repo: Path) -> dict[str, list[tuple[str, str]]]:
    """Use ripgrep to find Python import statements and parse them.

    Returns:
        Mapping of ``{relative_file_path: [(raw_statement, dotted_module), ...]}``.
    """
    try:
        result = subprocess.run(
            ["rg", "-n", r"^(?:from|import)\s+", "--type", "py", "--json"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.debug(f"rg Python imports failed: {e}")
        return {}

    imports: dict[str, list[tuple[str, str]]] = {}
    if not result.stdout:
        return imports

    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("type") != "match":
            continue

        match_data = data.get("data", {})
        file_path = match_data.get("path", {}).get("text", "")
        line_text = match_data.get("lines", {}).get("text", "").strip()

        if not file_path or not line_text:
            continue

        module = _parse_python_import_line(line_text)
        if module:
            imports.setdefault(file_path, []).append((line_text, module))

    return imports


def _rg_js_imports(repo: Path) -> dict[str, list[tuple[str, str]]]:
    """Use ripgrep to find JS/TS import/require statements and parse them.

    Returns:
        Mapping of ``{relative_file_path: [(raw_statement, module_specifier), ...]}``.
    """
    try:
        result = subprocess.run(
            ["rg", "-n", r"(?:import\s+|require\s*\()", "--type", "ts", "--type", "js", "--json"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.debug(f"rg JS/TS imports failed: {e}")
        return {}

    imports: dict[str, list[tuple[str, str]]] = {}
    if not result.stdout:
        return imports

    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("type") != "match":
            continue

        match_data = data.get("data", {})
        file_path = match_data.get("path", {}).get("text", "")
        line_text = match_data.get("lines", {}).get("text", "").strip()

        if not file_path or not line_text:
            continue

        # Try `import ... from '...'`
        m = _JS_IMPORT_FROM.search(line_text)
        if m:
            module = m.group(1)
            imports.setdefault(file_path, []).append((line_text, module))
            continue

        # Try `require('...')`
        m = _JS_REQUIRE.search(line_text)
        if m:
            module = m.group(1)
            imports.setdefault(file_path, []).append((line_text, module))
            continue

    return imports


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


def _run_semantic_enrichment(graph: CodeGraph, repo: Path, out: Path, files: list[str], quiet: bool) -> None:
    """Step 11a: Run semantic embedding enrichment (optional).

    Chunks source code at function/method level via tree-sitter, embeds via
    Voyage Code 3 or Bedrock Cohere Embed 4, builds cosine similarity edges,
    and runs community detection. Adds SIMILAR_TO edges to the graph.

    This step is entirely optional -- if dependencies are missing, API keys
    are not configured, or embedding_enabled is False, it is silently skipped.
    """
    settings = get_settings()
    if not settings.embedding_enabled:
        if not quiet:
            logger.info("Semantic enrichment disabled (embedding_enabled=False)")
        return

    try:
        from code_context_agent.tools.graph.embeddings import run_semantic_enrichment

        edge_count = run_semantic_enrichment(graph, repo, out, files, settings)
        if not quiet and edge_count:
            logger.info(f"Semantic enrichment: {edge_count} SIMILAR_TO edges added")
    except ImportError as e:
        logger.warning(f"Semantic enrichment unavailable (missing dependency): {e}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Semantic enrichment failed (non-fatal): {e}")


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


# --------------------------------------------------------------------------- #
# Steps 14-21: Extended static analysis
# --------------------------------------------------------------------------- #


def _run_semgrep_auto(repo: Path, out: Path, quiet: bool) -> None:
    """Step 14: Run semgrep with auto config for general findings."""
    if shutil.which("semgrep") is None:
        logger.debug("semgrep not found -- skipping semgrep auto scan")
        return

    try:
        result = subprocess.run(
            ["semgrep", "--config", "auto", "--json", "--quiet", str(repo)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.stdout:
            (out / "semgrep_auto.json").write_text(result.stdout)
            if not quiet:
                logger.info(f"Semgrep auto: wrote {out / 'semgrep_auto.json'}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Semgrep auto scan failed: {e}")


def _run_semgrep_owasp(repo: Path, out: Path, quiet: bool) -> None:
    """Step 15: Run semgrep with OWASP Top Ten config."""
    if shutil.which("semgrep") is None:
        logger.debug("semgrep not found -- skipping semgrep OWASP scan")
        return

    try:
        result = subprocess.run(
            ["semgrep", "--config", "p/owasp-top-ten", "--json", "--quiet", str(repo)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.stdout:
            (out / "semgrep_owasp.json").write_text(result.stdout)
            if not quiet:
                logger.info(f"Semgrep OWASP: wrote {out / 'semgrep_owasp.json'}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Semgrep OWASP scan failed: {e}")


def _run_typecheck(repo: Path, out: Path, lang_files: dict[str, list[str]], quiet: bool) -> None:
    """Step 16: Run type checker (ty or pyright) for Python projects."""
    if "py" not in lang_files:
        return

    # Try ty first
    if shutil.which("ty"):
        try:
            result = subprocess.run(
                ["ty", "check", "--output-format", "json"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.stdout:
                (out / "typecheck.json").write_text(result.stdout)
                if not quiet:
                    logger.info(f"Type check (ty): wrote {out / 'typecheck.json'}")
                return
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"ty check failed: {e}")

    # Fallback to pyright
    if shutil.which("pyright"):
        try:
            result = subprocess.run(
                ["pyright", "--outputjson"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.stdout:
                (out / "typecheck.json").write_text(result.stdout)
                if not quiet:
                    logger.info(f"Type check (pyright): wrote {out / 'typecheck.json'}")
                return
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"pyright check failed: {e}")

    logger.debug("No type checker (ty or pyright) found -- skipping type check")


def _run_lint(repo: Path, out: Path, quiet: bool) -> None:
    """Step 17: Run ruff linter."""
    if shutil.which("ruff") is None:
        logger.debug("ruff not found -- skipping lint")
        return

    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format", "json", str(repo)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # ruff returns exit code 1 when it finds violations (normal, not an error)
        if result.stdout:
            # Validate it's parseable JSON before writing
            try:
                json.loads(result.stdout)
                (out / "lint.json").write_text(result.stdout)
                if not quiet:
                    logger.info(f"Lint (ruff): wrote {out / 'lint.json'}")
            except json.JSONDecodeError:
                logger.debug("ruff output is not valid JSON")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Ruff lint failed: {e}")


def _run_complexity(repo: Path, out: Path, lang_files: dict[str, list[str]], quiet: bool) -> None:
    """Step 18: Run radon cyclomatic complexity analysis."""
    if "py" not in lang_files:
        return

    if shutil.which("radon") is None:
        logger.debug("radon not found -- skipping complexity analysis")
        return

    try:
        result = subprocess.run(
            ["radon", "cc", "-j", str(repo)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            (out / "complexity.json").write_text(result.stdout)
            if not quiet:
                logger.info(f"Complexity (radon): wrote {out / 'complexity.json'}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Radon complexity analysis failed: {e}")


def _run_dead_code_py(repo: Path, out: Path, lang_files: dict[str, list[str]], quiet: bool) -> None:
    """Step 19: Run vulture dead code detection for Python."""
    if "py" not in lang_files:
        return

    if shutil.which("vulture") is None:
        logger.debug("vulture not found -- skipping Python dead code detection")
        return

    try:
        result = subprocess.run(
            ["vulture", str(repo), "--min-confidence", "80"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # vulture outputs text lines, not JSON -- parse them
        pattern = re.compile(r"^(.+?):(\d+): (.+)$")
        entries: list[dict[str, Any]] = []
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                m = pattern.match(line.strip())
                if m:
                    entries.append({"file": m.group(1), "line": int(m.group(2)), "message": m.group(3)})

        (out / "dead_code_py.json").write_text(json.dumps(entries, indent=2))
        if not quiet:
            logger.info(f"Dead code (vulture): {len(entries)} findings -> {out / 'dead_code_py.json'}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Vulture dead code detection failed: {e}")


def _run_dead_code_ts(repo: Path, out: Path, lang_files: dict[str, list[str]], quiet: bool) -> None:
    """Step 20: Run knip dead code detection for TypeScript/JavaScript."""
    if "ts" not in lang_files:
        return

    if shutil.which("npx") is None:
        logger.debug("npx not found -- skipping TS/JS dead code detection")
        return

    try:
        result = subprocess.run(
            ["npx", "-y", "knip@5", "--reporter", "json"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            (out / "dead_code_ts.json").write_text(result.stdout)
            if not quiet:
                logger.info(f"Dead code (knip): wrote {out / 'dead_code_ts.json'}")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Knip dead code detection failed: {e}")


def _run_deps(repo: Path, out: Path, lang_files: dict[str, list[str]], quiet: bool) -> None:
    """Step 21: Generate dependency graph."""
    if "py" in lang_files and shutil.which("pipdeptree"):
        try:
            result = subprocess.run(
                ["pipdeptree", "--json"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout:
                (out / "deps.json").write_text(result.stdout)
                if not quiet:
                    logger.info(f"Dependencies (pipdeptree): wrote {out / 'deps.json'}")
            return
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"pipdeptree failed: {e}")

    if "ts" in lang_files and shutil.which("npm"):
        try:
            result = subprocess.run(
                ["npm", "ls", "--json", "--depth=1"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout:
                (out / "deps.json").write_text(result.stdout)
                if not quiet:
                    logger.info(f"Dependencies (npm): wrote {out / 'deps.json'}")
            return
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"npm ls failed: {e}")

    logger.debug("No dependency tool available -- skipping dependency graph")


# --------------------------------------------------------------------------- #
# Heuristic summary helpers
# --------------------------------------------------------------------------- #


def _count_total_lines(repo: Path, files: list[str]) -> int:
    """Count total lines across all files (capped at 5000 files for perf)."""
    total = 0
    for f in files[:5000]:
        try:
            total += (repo / f).read_bytes().count(b"\n")
        except (OSError, ValueError):
            continue
    return total


def _extract_token_count(orientation_path: Path) -> int | None:
    """Parse repomix orientation file for a token count line."""
    if not orientation_path.exists():
        return None
    try:
        text = orientation_path.read_text(errors="replace")
        # Look for patterns like "Token count: 123456" or "Tokens: 123,456"
        m = re.search(r"[Tt]oken[s]?\s*(?:count)?[:\s]+([0-9][0-9,_]*)", text)
        if m:
            return int(m.group(1).replace(",", "").replace("_", ""))
    except (OSError, ValueError):
        pass  # Orientation file missing or unparseable — fall through to None
    return None


def _load_json_artifact(path: Path) -> Any | None:
    """Load a JSON artifact, returning None on missing or parse error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _count_semgrep_by_severity(data: Any) -> dict[str, int]:
    """Parse semgrep JSON and count findings by severity."""
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    if not isinstance(data, dict):
        return counts
    results = data.get("results", [])
    if not isinstance(results, list):
        return counts
    for item in results:
        severity = str(item.get("extra", {}).get("severity", "info")).lower()
        if severity in counts:
            counts[severity] += 1
        else:
            counts["info"] += 1
    return counts


def _count_owasp_by_category(data: Any) -> dict[str, int]:
    """Parse semgrep OWASP JSON and group findings by check_id prefix."""
    categories: dict[str, int] = {}
    if not isinstance(data, dict):
        return categories
    results = data.get("results", [])
    if not isinstance(results, list):
        return categories
    for item in results:
        check_id = str(item.get("check_id", "unknown"))
        # Extract category from check_id (e.g. "python.django.security.injection.sql" -> "injection")
        parts = check_id.split(".")
        # Use the broadest meaningful segment -- typically after "security" or 3rd segment
        _min_owasp_depth = 3
        category = check_id
        if len(parts) >= _min_owasp_depth:
            category = parts[2] if len(parts) > _min_owasp_depth else parts[-1]
        categories[category] = categories.get(category, 0) + 1
    return categories


def _count_type_errors(data: Any) -> int:
    """Count type errors from ty or pyright output."""
    if not isinstance(data, (dict, list)):
        return 0
    # ty outputs a JSON list of diagnostics
    if isinstance(data, list):
        return len(data)
    # pyright outputs a dict with generalDiagnostics
    diagnostics = data.get("generalDiagnostics", [])
    if isinstance(diagnostics, list):
        return len(diagnostics)
    return 0


def _count_dead_code(out: Path) -> int:
    """Count total dead code findings from Python and TS artifacts."""
    total = 0
    py_data = _load_json_artifact(out / "dead_code_py.json")
    if isinstance(py_data, list):
        total += len(py_data)
    ts_data = _load_json_artifact(out / "dead_code_ts.json")
    if isinstance(ts_data, list):
        total += len(ts_data)
    elif isinstance(ts_data, dict):
        # knip JSON may have arrays under various keys
        for v in ts_data.values():
            if isinstance(v, list):
                total += len(v)
    return total


def _avg_complexity(data: Any) -> float:
    """Compute mean cyclomatic complexity from radon cc JSON output.

    Radon outputs a dict of filepath -> list of function dicts, each with a
    ``complexity`` field.
    """
    if not isinstance(data, dict):
        return 0.0
    all_cc: list[float] = []
    for funcs in data.values():
        if not isinstance(funcs, list):
            continue
        for func in funcs:
            if isinstance(func, dict) and "complexity" in func:
                all_cc.append(float(func["complexity"]))
    if not all_cc:
        return 0.0
    return round(statistics.mean(all_cc), 2)


def _extract_top_complex_functions(data: Any, top_k: int = 10) -> list[dict[str, Any]]:
    """Extract top N functions by cyclomatic complexity from radon output."""
    if not isinstance(data, dict):
        return []
    entries: list[dict[str, Any]] = []
    for filepath, funcs in data.items():
        if not isinstance(funcs, list):
            continue
        for func in funcs:
            if not isinstance(func, dict) or "complexity" not in func:
                continue
            entries.append(
                {
                    "name": func.get("name", "unknown"),
                    "file": filepath,
                    "lines": f"{func.get('lineno', 0)}-{func.get('endline', func.get('lineno', 0))}",
                    "complexity": func.get("complexity", 0),
                },
            )
    entries.sort(key=lambda x: x["complexity"], reverse=True)
    return entries[:top_k]


def _compute_bus_factor_risks(repo: Path, files: list[str]) -> list[str]:
    """Find directories with a single contributor (bus factor risk).

    For each directory with >5 files, count distinct git authors. Cap to
    20 directories for performance.
    """
    dir_files: dict[str, int] = {}
    for f in files:
        parent = str(Path(f).parent)
        if parent == ".":
            continue
        dir_files[parent] = dir_files.get(parent, 0) + 1

    # Only check directories with >5 files, capped at 20
    _min_dir_files = 5
    candidate_dirs = sorted(
        ((d, c) for d, c in dir_files.items() if c > _min_dir_files),
        key=lambda x: x[1],
        reverse=True,
    )[:20]

    risks: list[str] = []
    for dir_path, file_count in candidate_dirs:
        try:
            result = subprocess.run(
                ["git", "log", "--format=%aN", "--", f"{dir_path}/"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout:
                authors = set(result.stdout.strip().splitlines())
                if len(authors) <= 1:
                    risks.append(f"{dir_path} ({len(authors)} contributor, {file_count} files)")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            continue

    return risks


def _count_contributors(repo: Path) -> int:
    """Count distinct contributors via git shortlog."""
    try:
        result = subprocess.run(
            ["git", "shortlog", "-sn", "--all", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return len([line for line in result.stdout.strip().splitlines() if line.strip()])
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        pass  # git shortlog unavailable or timed out — fall through to 0
    return 0


def _get_total_commits(repo: Path) -> int:
    """Count total commits via git rev-list."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, ValueError):
        pass  # git rev-list unavailable or timed out — fall through to 0
    return 0


# --------------------------------------------------------------------------- #
# Heuristic summary generation
# --------------------------------------------------------------------------- #


def _build_health_section(out: Path, graph_stats: dict[str, Any]) -> dict[str, Any]:
    """Build the health section of the heuristic summary from index artifacts."""
    semgrep_data = _load_json_artifact(out / "semgrep_auto.json")
    semgrep_severities = _count_semgrep_by_severity(semgrep_data) if semgrep_data else {}

    owasp_data = _load_json_artifact(out / "semgrep_owasp.json")
    owasp_categories = _count_owasp_by_category(owasp_data) if owasp_data else {}

    typecheck_data = _load_json_artifact(out / "typecheck.json")
    type_error_count = _count_type_errors(typecheck_data) if typecheck_data else 0

    lint_data = _load_json_artifact(out / "lint.json")
    lint_count = len(lint_data) if isinstance(lint_data, list) else 0

    complexity_data = _load_json_artifact(out / "complexity.json")
    avg_cc = _avg_complexity(complexity_data) if complexity_data else 0.0

    return {
        "semgrep_findings": semgrep_severities,
        "owasp_findings": owasp_categories,
        "type_errors": type_error_count,
        "lint_violations": lint_count,
        "dead_code_symbols": _count_dead_code(out),
        "clone_groups": graph_stats.get("edge_types", {}).get("similar_to", 0),
        "avg_cyclomatic_complexity": avg_cc,
    }


def _build_topology_section(
    graph: CodeGraph,
    graph_stats: dict[str, Any],
    repo: Path,
    files: list[str],
) -> dict[str, Any]:
    """Build the topology section of the heuristic summary."""
    import networkx as nx

    from code_context_agent.tools.graph.analysis import CodeAnalyzer

    view = graph.get_view()

    try:
        components = nx.number_weakly_connected_components(view)
    except Exception:  # noqa: BLE001
        components = 0

    # Fan-in / fan-out
    max_fi_node, max_fi_count = "", 0
    max_fo_node, max_fo_count = "", 0
    try:
        if view.number_of_nodes() > 0:
            in_degrees = dict(view.in_degree())
            if in_degrees:
                max_fi_node = max(in_degrees, key=lambda k: in_degrees[k])
                max_fi_count = in_degrees[max_fi_node]
            out_degrees = dict(view.out_degree())
            if out_degrees:
                max_fo_node = max(out_degrees, key=lambda k: out_degrees[k])
                max_fo_count = out_degrees[max_fo_node]
    except Exception:  # noqa: BLE001
        logger.debug("Fan-in/fan-out computation failed")

    # Entry points and hotspots
    analyzer = CodeAnalyzer(graph)
    try:
        entry_points = analyzer.find_entry_points()[:10]
    except Exception:  # noqa: BLE001
        entry_points = []

    try:
        hotspots = analyzer.find_hotspots(10)
    except Exception:  # noqa: BLE001
        hotspots = []

    return {
        "graph_nodes": graph_stats.get("node_count", 0),
        "graph_edges": graph_stats.get("edge_count", 0),
        "connected_components": components,
        "max_fan_in": {"node": max_fi_node, "count": max_fi_count},
        "max_fan_out": {"node": max_fo_node, "count": max_fo_count},
        "entry_points": [ep.get("id", "") for ep in entry_points],
        "hotspots": [h.get("id", "") for h in hotspots],
        "bus_factor_risks": _compute_bus_factor_risks(repo, files),
    }


def _build_git_section(graph: CodeGraph, repo: Path) -> dict[str, Any]:
    """Build the git section of the heuristic summary."""
    from code_context_agent.tools.graph.model import EdgeType

    coupled_pairs: list[str] = []
    try:
        cochange_edges = graph.get_edges_by_type(EdgeType.COCHANGES)
        sorted_edges = sorted(cochange_edges, key=lambda e: e[2].get("weight", 0), reverse=True)
        coupled_pairs = [f"{e[0]} <-> {e[1]}" for e in sorted_edges[:10]]
    except Exception:  # noqa: BLE001
        logger.debug("Coupled pairs extraction failed")

    return {
        "total_commits_analyzed": _get_total_commits(repo),
        "active_contributors": _count_contributors(repo),
        "most_coupled_pairs": coupled_pairs[:5],
    }


def _generate_heuristic_summary(
    graph: CodeGraph,
    graph_stats: dict[str, Any],
    files: list[str],
    lang_files: dict[str, list[str]],
    frameworks: list[str],
    out: Path,
    repo: Path,
    quiet: bool,
) -> dict[str, Any]:
    """Aggregate all index outputs into heuristic_summary.json.

    This is the bridge artifact between cheap deterministic indexing and
    expensive LLM inference -- it tells the coordinator what to focus on.
    """
    total_lines = _count_total_lines(repo, files)
    estimated_tokens = _extract_token_count(out / "CONTEXT.orientation.md")

    node_types = graph_stats.get("node_types", {})
    complexity_data = _load_json_artifact(out / "complexity.json")
    top_complex = _extract_top_complex_functions(complexity_data) if complexity_data else []

    summary: dict[str, Any] = {
        "volume": {
            "total_files": len(files),
            "total_lines": total_lines,
            "estimated_tokens": estimated_tokens or int(total_lines * 2.5),
            "languages": {lang: len(fs) for lang, fs in lang_files.items()},
            "frameworks": frameworks,
        },
        "symbols": {
            "functions": node_types.get("function", 0),
            "classes": node_types.get("class", 0),
            "modules": node_types.get("module", 0),
            "top_complex_functions": top_complex,
        },
        "health": _build_health_section(out, graph_stats),
        "topology": _build_topology_section(graph, graph_stats, repo, files),
        "git": _build_git_section(graph, repo),
    }

    summary_path = out / "heuristic_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    if not quiet:
        logger.info(f"Heuristic summary: {summary_path}")

    return summary
