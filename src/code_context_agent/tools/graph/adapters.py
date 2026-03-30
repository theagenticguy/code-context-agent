"""Input adapters for converting tool outputs to graph elements.

This module provides functions to ingest outputs from:
- LSP tools (symbols, references, definitions)
- AST-grep tools (pattern matches, rule pack results)
- ripgrep tools (text matches)
- Test file mappings
"""

from __future__ import annotations

import itertools
import posixpath
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from .model import CodeEdge, CodeNode, EdgeType, NodeType, lsp_kind_to_node_type

if TYPE_CHECKING:
    from .model import CodeGraph


def _uri_to_path(uri: str) -> str:
    """Convert a file:// URI to a filesystem path.

    Args:
        uri: A file:// URI string

    Returns:
        Filesystem path string
    """
    parsed = urlparse(uri)
    return unquote(parsed.path)


def _make_symbol_id(file_path: str, name: str, line: int | None = None) -> str:
    """Create a unique symbol ID.

    Args:
        file_path: Path to the source file
        name: Symbol name
        line: Optional line number for disambiguation

    Returns:
        Unique identifier string
    """
    if line is not None:
        return f"{file_path}:{name}:{line}"
    return f"{file_path}:{name}"


def _make_location_id(file_path: str, line: int) -> str:
    """Create a location-based ID for references.

    Args:
        file_path: Path to the source file
        line: Line number

    Returns:
        Location identifier string
    """
    return f"{file_path}:L{line}"


def ingest_lsp_symbols(
    symbols_result: dict[str, Any],
    file_path: str,
) -> tuple[list[CodeNode], list[CodeEdge]]:
    """Convert lsp_document_symbols output to CodeNodes and containment edges.

    Args:
        symbols_result: JSON result from lsp_document_symbols tool
        file_path: Path to the source file

    Returns:
        Tuple of (nodes, edges) where edges represent containment relationships
    """
    nodes: list[CodeNode] = []
    edges: list[CodeEdge] = []

    if symbols_result.get("status") != "success":
        return nodes, edges

    def process_symbol(
        symbol: dict[str, Any],
        parent_id: str | None = None,
    ) -> None:
        """Recursively process a symbol and its children."""
        name = symbol.get("name", "")
        kind = symbol.get("kind", 13)  # Default to Variable
        range_data = symbol.get("range", {})

        line_start = range_data.get("start", {}).get("line", 0)
        line_end = range_data.get("end", {}).get("line", line_start)

        node_id = _make_symbol_id(file_path, name, line_start)
        node_type = lsp_kind_to_node_type(kind)

        node = CodeNode(
            id=node_id,
            name=name,
            node_type=node_type,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            metadata={"lsp_kind": kind},
        )
        nodes.append(node)

        # Create containment edge from parent
        if parent_id is not None:
            edges.append(
                CodeEdge(
                    source=parent_id,
                    target=node_id,
                    edge_type=EdgeType.CONTAINS,
                    confidence=0.95,
                ),
            )

        # Process children recursively
        for child in symbol.get("children", []):
            process_symbol(child, parent_id=node_id)

    # Process top-level symbols
    for symbol in symbols_result.get("symbols", []):
        process_symbol(symbol)

    return nodes, edges


def ingest_lsp_references(
    references_result: dict[str, Any],
    source_node_id: str,
) -> list[CodeEdge]:
    """Convert lsp_references output to reference edges.

    Creates edges from each reference location back to the source symbol.
    The source is the referrer, target is the referenced symbol.

    Args:
        references_result: JSON result from lsp_references tool
        source_node_id: ID of the symbol being referenced

    Returns:
        List of CodeEdge objects representing references
    """
    edges: list[CodeEdge] = []

    if references_result.get("status") != "success":
        return edges

    for ref in references_result.get("references", []):
        uri = ref.get("uri", "")
        range_data = ref.get("range", {})
        line = range_data.get("start", {}).get("line", 0)

        file_path = _uri_to_path(uri)
        referrer_id = _make_location_id(file_path, line)

        edges.append(
            CodeEdge(
                source=referrer_id,
                target=source_node_id,
                edge_type=EdgeType.REFERENCES,
                confidence=0.95,
                metadata={
                    "file": file_path,
                    "line": line,
                },
            ),
        )

    return edges


def ingest_lsp_definition(
    definition_result: dict[str, Any],
    from_file: str,
    from_line: int,
) -> list[CodeEdge]:
    """Convert lsp_definition output to import/call edges.

    Creates edges from the usage location to the definition location.

    Args:
        definition_result: JSON result from lsp_definition tool
        from_file: File where the symbol is used
        from_line: Line where the symbol is used

    Returns:
        List of CodeEdge objects representing the definition relationship
    """
    edges: list[CodeEdge] = []

    if definition_result.get("status") != "success":
        return edges

    source_id = _make_location_id(from_file, from_line)

    for defn in definition_result.get("definitions", []):
        uri = defn.get("uri", "")
        range_data = defn.get("range", {})
        line = range_data.get("start", {}).get("line", 0)

        target_file = _uri_to_path(uri)
        target_id = _make_location_id(target_file, line)

        # Determine edge type: IMPORTS if different file, CALLS if same file
        edge_type = EdgeType.IMPORTS if target_file != from_file else EdgeType.CALLS

        edges.append(
            CodeEdge(
                source=source_id,
                target=target_id,
                edge_type=edge_type,
                confidence=0.95,
                metadata={
                    "from_file": from_file,
                    "to_file": target_file,
                    "to_line": line,
                },
            ),
        )

    return edges


def ingest_astgrep_matches(
    matches_result: dict[str, Any],
) -> list[CodeNode]:
    """Convert astgrep_scan output to CodeNodes.

    Each match becomes a PATTERN_MATCH node with the pattern in metadata.

    Args:
        matches_result: JSON result from astgrep_scan tool

    Returns:
        List of CodeNode objects representing pattern matches
    """
    nodes: list[CodeNode] = []

    if matches_result.get("status") not in ("success", "no_matches"):
        return nodes

    pattern = matches_result.get("pattern", "")

    for match in matches_result.get("matches", []):
        file_path = match.get("file", "")
        range_data = match.get("range", {})
        line_start = range_data.get("start", {}).get("line", 0)
        line_end = range_data.get("end", {}).get("line", line_start)
        text = match.get("text", "")

        node_id = _make_location_id(file_path, line_start)

        nodes.append(
            CodeNode(
                id=node_id,
                name=text[:50] if len(text) > 50 else text,  # Truncate long matches
                node_type=NodeType.PATTERN_MATCH,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                metadata={
                    "pattern": pattern,
                    "full_text": text,
                },
            ),
        )

    return nodes


def ingest_astgrep_rule_pack(
    rule_pack_result: dict[str, Any],
) -> list[CodeNode]:
    """Convert astgrep_scan_rule_pack output to CodeNodes.

    Each match becomes a PATTERN_MATCH node with rule_id and category in metadata.

    Args:
        rule_pack_result: JSON result from astgrep_scan_rule_pack tool

    Returns:
        List of CodeNode objects representing categorized matches
    """
    nodes: list[CodeNode] = []

    if rule_pack_result.get("status") not in ("success", "no_matches"):
        return nodes

    matches_by_rule = rule_pack_result.get("matches_by_rule", {})

    for rule_id, matches in matches_by_rule.items():
        for match in matches:
            file_path = match.get("file", "")
            range_data = match.get("range", {})
            line_start = range_data.get("start", {}).get("line", 0)
            line_end = range_data.get("end", {}).get("line", line_start)
            text = match.get("text", "")
            message = match.get("message", "")

            node_id = f"{file_path}:L{line_start}:{rule_id}"

            # Extract category from rule_id (e.g., "ts-db-write" -> "db")
            category = _extract_category_from_rule_id(rule_id)

            nodes.append(
                CodeNode(
                    id=node_id,
                    name=text[:50] if len(text) > 50 else text,
                    node_type=NodeType.PATTERN_MATCH,
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    metadata={
                        "rule_id": rule_id,
                        "category": category,
                        "message": message,
                        "full_text": text,
                    },
                ),
            )

    return nodes


def _extract_category_from_rule_id(rule_id: str) -> str:
    """Extract a category from a rule ID.

    Examples:
        "ts-db-write-operation" -> "db"
        "py-auth-jwt" -> "auth"
        "ts-http-post" -> "http"

    Args:
        rule_id: The rule identifier

    Returns:
        Category string
    """
    # Common category patterns
    categories = ["db", "auth", "http", "graphql", "state", "event", "cache", "websocket"]

    lower_id = rule_id.lower()
    for cat in categories:
        if cat in lower_id:
            return cat

    # Default: second segment of rule ID
    parts = rule_id.split("-")
    return parts[1] if len(parts) > 1 else "unknown"


def ingest_rg_matches(
    rg_result: dict[str, Any],
) -> list[CodeNode]:
    """Convert rg_search output to preliminary CodeNodes.

    Creates nodes for text matches that can be refined by LSP later.

    Args:
        rg_result: JSON result from rg_search tool

    Returns:
        List of CodeNode objects representing text matches
    """
    nodes: list[CodeNode] = []

    if rg_result.get("status") != "success":
        return nodes

    pattern = rg_result.get("pattern", "")

    for match in rg_result.get("matches", []):
        file_path = match.get("path", "")
        line = match.get("line_number", 1)
        text = match.get("lines", "").strip()

        node_id = _make_location_id(file_path, line)

        nodes.append(
            CodeNode(
                id=node_id,
                name=text[:50] if len(text) > 50 else text,
                node_type=NodeType.PATTERN_MATCH,
                file_path=file_path,
                line_start=line,
                line_end=line,
                metadata={
                    "pattern": pattern,
                    "full_text": text,
                    "source": "rg",
                },
            ),
        )

    return nodes


def ingest_inheritance(
    hover_content: str,
    class_node_id: str,
    file_path: str,
) -> list[CodeEdge]:
    """Extract inheritance relationships from LSP hover info.

    Parses type signatures to find extends/implements relationships.

    Args:
        hover_content: The hover content string (may be markdown)
        class_node_id: ID of the class node
        file_path: Path to the file containing the class

    Returns:
        List of CodeEdge objects representing inheritance
    """
    edges: list[CodeEdge] = []

    # TypeScript patterns
    # class Foo extends Bar implements IBaz, IQux
    ts_extends = re.search(r"class\s+\w+\s+extends\s+(\w+)", hover_content)
    ts_implements = re.findall(r"implements\s+([\w,\s]+)", hover_content)

    if ts_extends:
        base_class = ts_extends.group(1)
        edges.append(
            CodeEdge(
                source=class_node_id,
                target=f"{file_path}:{base_class}",
                edge_type=EdgeType.INHERITS,
                confidence=0.85,
                metadata={"language": "typescript"},
            ),
        )

    for impl_match in ts_implements:
        interfaces = [i.strip() for i in impl_match.split(",")]
        for iface in interfaces:
            if iface:
                edges.append(
                    CodeEdge(
                        source=class_node_id,
                        target=f"{file_path}:{iface}",
                        edge_type=EdgeType.IMPLEMENTS,
                        confidence=0.85,
                        metadata={"language": "typescript"},
                    ),
                )

    # Python patterns
    # class Foo(Bar, Baz):
    py_bases = re.search(r"class\s+\w+\s*\(([^)]+)\)", hover_content)
    if py_bases:
        bases = [b.strip() for b in py_bases.group(1).split(",")]
        for base in bases:
            # Skip common non-inheritance bases
            if base and base not in ("object", "ABC", "Protocol"):
                edges.append(
                    CodeEdge(
                        source=class_node_id,
                        target=f"{file_path}:{base}",
                        edge_type=EdgeType.INHERITS,
                        confidence=0.85,
                        metadata={"language": "python"},
                    ),
                )

    return edges


def ingest_test_mapping(
    test_files: list[str],
    production_files: list[str],
) -> list[CodeEdge]:
    """Create test coverage edges based on file naming conventions.

    Maps test files to production files using common naming patterns:
    - test_foo.py -> foo.py
    - foo_test.py -> foo.py
    - foo.test.ts -> foo.ts
    - __tests__/foo.js -> foo.js

    Args:
        test_files: List of test file paths
        production_files: List of production file paths

    Returns:
        List of CodeEdge objects representing test-to-production relationships
    """
    edges: list[CodeEdge] = []

    # Build a lookup map for production files by name
    prod_by_name: dict[str, str] = {}
    for prod_file in production_files:
        name = Path(prod_file).stem
        prod_by_name[name.lower()] = prod_file

    for test_file in test_files:
        prod_file = _match_test_to_prod(test_file, prod_by_name)
        if prod_file:
            edges.append(
                CodeEdge(
                    source=test_file,
                    target=prod_file,
                    edge_type=EdgeType.TESTS,
                    confidence=0.70,
                    metadata={"convention": "name_match"},
                ),
            )

    return edges


def _match_test_to_prod(
    test_file: str,
    prod_by_name: dict[str, str],
) -> str | None:
    """Match a test file to its corresponding production file.

    Args:
        test_file: Path to the test file
        prod_by_name: Map of lowercase production file names to paths

    Returns:
        Production file path if found, None otherwise
    """
    path = Path(test_file)
    stem = path.stem.lower()

    # Remove common test prefixes/suffixes
    patterns = [
        (r"^test_", ""),  # test_foo -> foo
        (r"_test$", ""),  # foo_test -> foo
        (r"\.test$", ""),  # foo.test -> foo
        (r"\.spec$", ""),  # foo.spec -> foo
        (r"^tests?_", ""),  # tests_foo -> foo
    ]

    for pattern, replacement in patterns:
        candidate = re.sub(pattern, replacement, stem)
        if candidate != stem and candidate in prod_by_name:
            return prod_by_name[candidate]

    # Check if the stem directly matches (for __tests__/foo.js -> foo.js cases)
    if stem in prod_by_name:
        return prod_by_name[stem]

    return None


def ingest_git_cochanges(
    cochanges_result: dict[str, Any],
    min_percentage: float = 20.0,
) -> list[CodeEdge]:
    """Convert git_files_changed_together output to co-change edges.

    Creates bidirectional edges between files that frequently change together,
    with weight based on co-change frequency.

    Args:
        cochanges_result: JSON result from git_files_changed_together tool
        min_percentage: Minimum co-change percentage to create an edge (default 20%)

    Returns:
        List of CodeEdge objects representing co-change relationships

    Example:
        >>> result = json.loads(git_files_changed_together("/repo", "src/auth.py"))
        >>> edges = ingest_git_cochanges(result, min_percentage=15.0)
    """
    edges: list[CodeEdge] = []

    if cochanges_result.get("status") != "success":
        return edges

    source_file = cochanges_result.get("file_path", "")
    if not source_file:
        return edges

    for cochange in cochanges_result.get("cochanged_files", []):
        percentage = cochange.get("percentage", 0)
        if percentage < min_percentage:
            continue

        target_file = cochange.get("path", "")
        if not target_file:
            continue

        # Weight is normalized co-change frequency (0-1)
        weight = percentage / 100.0

        edges.append(
            CodeEdge(
                source=source_file,
                target=target_file,
                edge_type=EdgeType.COCHANGES,
                weight=weight,
                confidence=0.60,
                metadata={
                    "count": cochange.get("count", 0),
                    "percentage": percentage,
                    "source": "git_cochanges",
                },
            ),
        )

    return edges


def ingest_git_hotspots(
    hotspots_result: dict[str, Any],
) -> list[CodeNode]:
    """Convert git_hotspots output to file nodes with churn metadata.

    Creates FILE nodes for each hotspot with commit frequency in metadata.
    This helps identify files that may need attention.

    Args:
        hotspots_result: JSON result from git_hotspots tool

    Returns:
        List of CodeNode objects representing hotspot files
    """
    nodes: list[CodeNode] = []

    if hotspots_result.get("status") != "success":
        return nodes

    for hotspot in hotspots_result.get("hotspots", []):
        file_path = hotspot.get("path", "")
        if not file_path:
            continue

        nodes.append(
            CodeNode(
                id=file_path,
                name=Path(file_path).name,
                node_type=NodeType.FILE,
                file_path=file_path,
                line_start=0,
                line_end=0,
                metadata={
                    "commits": hotspot.get("commits", 0),
                    "churn_percentage": hotspot.get("percentage", 0),
                    "source": "git_hotspots",
                },
            ),
        )

    return nodes


def ingest_git_contributors(
    contributors_result: dict[str, Any],
    _file_path: str | None = None,
) -> dict[str, Any]:
    """Extract contributor metadata from git_contributors or git_blame_summary.

    Returns metadata that can be attached to file or repo nodes.

    Args:
        contributors_result: JSON result from git_contributors or git_blame_summary
        _file_path: Reserved for future use (file context for blame results)

    Returns:
        Dictionary of contributor metadata suitable for node metadata
    """
    if contributors_result.get("status") != "success":
        return {}

    # Handle both contributors and blame_summary formats
    authors = contributors_result.get("contributors") or contributors_result.get("authors", [])

    if not authors:
        return {}

    # Get primary contributor
    primary = authors[0] if authors else {}

    return {
        "primary_author": primary.get("email", ""),
        "author_count": len(authors),
        "authors": [a.get("email", "") for a in authors[:5]],  # Top 5
        "source": "git_contributors" if "contributors" in contributors_result else "git_blame",
    }


def ingest_clone_results(
    clone_result: dict[str, Any],
) -> list[CodeEdge]:
    """Convert clone detection results into SIMILAR_TO edges.

    Creates edges between files that share duplicate code blocks.

    Args:
        clone_result: JSON result from detect_clones tool

    Returns:
        List of CodeEdge objects with SIMILAR_TO type
    """
    if clone_result.get("status") != "success":
        return []

    edges: list[CodeEdge] = []
    clones = clone_result.get("clones", [])

    for clone in clones:
        first_file = clone.get("first_file", "")
        second_file = clone.get("second_file", "")

        if not first_file or not second_file:
            continue

        edges.append(
            CodeEdge(
                source=first_file,
                target=second_file,
                edge_type=EdgeType.SIMILAR_TO,
                confidence=0.75,
                metadata={
                    "first_start": clone.get("first_start", 0),
                    "first_end": clone.get("first_end", 0),
                    "second_start": clone.get("second_start", 0),
                    "second_end": clone.get("second_end", 0),
                    "duplicated_lines": clone.get("lines", 0),
                    "tokens": clone.get("tokens", 0),
                    "fragment": clone.get("fragment", ""),
                },
            ),
        )

    return edges


def ingest_static_imports(
    import_map: dict[str, list[dict[str, str]]],
    all_files: set[str],
) -> list[CodeEdge]:
    """Create IMPORTS edges between FILE nodes based on statically parsed import statements.

    Resolves imported module names to file paths within the repository and creates
    FILE-to-FILE IMPORTS edges for each successful resolution.

    Args:
        import_map: Mapping of ``{relative_file_path: [{"module": "dotted.module.name",
            "statement": "from X import Y"}]}``.
        all_files: Set of all relative file paths in the repository (for fast lookups).

    Returns:
        List of CodeEdge objects with ``EdgeType.IMPORTS`` between FILE nodes.
    """
    edges: list[CodeEdge] = []
    seen: set[tuple[str, str]] = set()

    for source_file, imports in import_map.items():
        for imp in imports:
            module = imp.get("module", "")
            statement = imp.get("statement", "")
            if not module:
                continue

            # Resolve relative imports for Python
            if module.startswith("."):
                resolved = _resolve_relative_import(source_file, module)
                if resolved is None:
                    continue
                module = resolved

            target_file = _resolve_module_to_file(module, source_file, all_files)
            if target_file is None or target_file == source_file:
                continue

            pair = (source_file, target_file)
            if pair in seen:
                continue
            seen.add(pair)

            edges.append(
                CodeEdge(
                    source=source_file,
                    target=target_file,
                    edge_type=EdgeType.IMPORTS,
                    confidence=0.90,
                    metadata={
                        "source": "static_import",
                        "import_statement": statement,
                    },
                ),
            )

    return edges


def _resolve_relative_import(source_file: str, module: str) -> str | None:
    """Resolve a Python relative import to an absolute dotted module path.

    Args:
        source_file: Relative path of the importing file (e.g. ``src/pkg/sub/foo.py``).
        module: Relative import module string (e.g. ``..bar`` or ``.utils``).

    Returns:
        Absolute dotted module path, or ``None`` if unresolvable.
    """
    # Count leading dots
    dots = 0
    for ch in module:
        if ch == ".":
            dots += 1
        else:
            break

    remainder = module[dots:]

    # Determine the package path of the source file
    source = Path(source_file)
    # Start from the parent directory of the source file
    package_parts = list(source.parent.parts)

    # Go up ``dots - 1`` levels (one dot = current package, two dots = parent, etc.)
    levels_up = dots - 1
    if levels_up > len(package_parts):
        return None
    if levels_up > 0:
        package_parts = package_parts[:-levels_up]

    if remainder:
        package_parts.append(remainder)

    return ".".join(package_parts)


def _resolve_module_to_file(
    module: str,
    source_file: str,
    all_files: set[str],
) -> str | None:
    """Resolve a dotted module name to a relative file path in the repository.

    Tries common file-path conventions for Python and JS/TS modules.

    Args:
        module: Dotted or path-based module name.
        source_file: The importing file (used to detect language).
        all_files: Set of all relative file paths for fast membership tests.

    Returns:
        Relative file path if resolved, ``None`` otherwise.
    """
    source_ext = Path(source_file).suffix.lower()

    if source_ext == ".py":
        return _resolve_python_module(module, all_files)
    if source_ext in {".ts", ".tsx", ".js", ".jsx"}:
        return _resolve_js_module(module, source_file, all_files)
    return None


def _resolve_python_module(module: str, all_files: set[str]) -> str | None:
    """Resolve a Python dotted module to a file path.

    Tries ``module/path.py`` and ``module/path/__init__.py``.

    Args:
        module: Dotted Python module name.
        all_files: Set of relative file paths.

    Returns:
        Matching relative file path or ``None``.
    """
    parts = module.replace(".", "/")

    # Try direct module file: a.b.c -> a/b/c.py
    candidate = f"{parts}.py"
    if candidate in all_files:
        return candidate

    # Try package init: a.b.c -> a/b/c/__init__.py
    candidate = f"{parts}/__init__.py"
    if candidate in all_files:
        return candidate

    return None


def _resolve_js_module(module: str, source_file: str, all_files: set[str]) -> str | None:
    """Resolve a JS/TS import specifier to a file path.

    Handles relative paths (``./foo``, ``../bar``) common in JS/TS projects.
    Does not resolve bare specifiers (npm packages).

    Args:
        module: Import specifier (e.g. ``./utils``, ``../components/Button``).
        source_file: The importing file path (for resolving relative paths).
        all_files: Set of relative file paths.

    Returns:
        Matching relative file path or ``None``.
    """
    # Only resolve relative imports (starting with . or ..)
    if not module.startswith("."):
        return None

    # Resolve relative to the importing file's directory and normalize ../
    source_dir = Path(source_file).parent
    resolved = (source_dir / module).as_posix()
    normalized = posixpath.normpath(resolved)

    # JS/TS extension candidates
    extensions = [".ts", ".tsx", ".js", ".jsx"]
    index_files = ["index.ts", "index.tsx", "index.js", "index.jsx"]

    # Try exact path (already has extension)
    if normalized in all_files:
        return normalized

    # Try adding extensions
    for ext in extensions:
        candidate = f"{normalized}{ext}"
        if candidate in all_files:
            return candidate

    # Try as directory with index file
    for index in index_files:
        candidate = f"{normalized}/{index}"
        if candidate in all_files:
            return candidate

    return None


def create_file_bridge_nodes(
    graph: CodeGraph,
) -> tuple[list[CodeNode], list[CodeEdge]]:
    """Create FILE nodes for each source file and CONTAINS edges to child symbols.

    Bridges the file-path/symbol-ID namespace gap so that git co-change,
    test mapping, and clone detection edges (which use raw file paths as
    node IDs) connect to the symbol subgraph (which uses
    ``file_path:symbol_name:line`` IDs).

    For each unique ``file_path`` found in existing symbol nodes, creates a
    FILE node whose ID is the raw file path (matching the format used by
    ``ingest_test_mapping``, ``ingest_git_cochanges``, and
    ``ingest_clone_results``), then adds a CONTAINS edge from that FILE node
    to every symbol node in the file.

    Args:
        graph: The CodeGraph to read existing nodes from.

    Returns:
        Tuple of (file_nodes, contains_edges) that were created.
    """
    # Collect symbol nodes grouped by their file_path attribute.
    # Skip nodes that are already FILE type (e.g. from git hotspots).
    file_to_symbols: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        node_type = data.get("node_type", "")
        file_path = data.get("file_path", "")
        if not file_path or node_type == NodeType.FILE.value:
            continue
        file_to_symbols.setdefault(file_path, []).append(node_id)

    nodes: list[CodeNode] = []
    edges: list[CodeEdge] = []

    for file_path, symbol_ids in file_to_symbols.items():
        # Only create a FILE node if one doesn't already exist for this path
        # (git hotspots may have already created one).
        if not graph.has_node(file_path):
            nodes.append(
                CodeNode(
                    id=file_path,
                    name=Path(file_path).name,
                    node_type=NodeType.FILE,
                    file_path=file_path,
                    line_start=0,
                    line_end=0,
                    metadata={"source": "file_bridge"},
                ),
            )

        for symbol_id in symbol_ids:
            edges.append(
                CodeEdge(
                    source=file_path,
                    target=symbol_id,
                    edge_type=EdgeType.CONTAINS,
                    confidence=0.95,
                    metadata={"source": "file_bridge"},
                ),
            )

    return nodes, edges


# Maximum category group size before representative sampling kicks in.
_MAX_CATEGORY_GROUP = 20


def create_category_edges(graph: CodeGraph) -> list[CodeEdge]:
    """Create SIMILAR_TO edges between nodes sharing the same AST-grep category.

    Groups PATTERN_MATCH nodes by their category metadata and creates edges
    between all pairs in each category group. Uses a representative sampling
    strategy to avoid quadratic edge explosion for large categories.

    Args:
        graph: CodeGraph with PATTERN_MATCH nodes that have category metadata.

    Returns:
        List of created CodeEdge instances.
    """
    # Group nodes by category
    category_groups: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        category = data.get("category")
        if category:
            category_groups.setdefault(category, []).append(node_id)

    edges: list[CodeEdge] = []

    for category, node_ids in category_groups.items():
        if len(node_ids) < 2:
            continue

        # Sample representative nodes for large groups
        if len(node_ids) > _MAX_CATEGORY_GROUP:
            sampled = random.Random(42).sample(node_ids, _MAX_CATEGORY_GROUP)  # noqa: S311
        else:
            sampled = node_ids

        for source, target in itertools.combinations(sampled, 2):
            edges.append(
                CodeEdge(
                    source=source,
                    target=target,
                    edge_type=EdgeType.SIMILAR_TO,
                    weight=0.8,
                    confidence=0.70,
                    metadata={"source": "category", "category": category},
                ),
            )

    return edges
