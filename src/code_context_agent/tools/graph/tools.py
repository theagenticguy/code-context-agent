"""Strands agent tools for code graph analysis.

This module exposes code graph functionality as @tool-decorated functions
that can be used by AI agents for codebase understanding.
"""

import json
from pathlib import Path
from typing import Any

from strands import tool

from .adapters import (
    ingest_astgrep_matches,
    ingest_astgrep_rule_pack,
    ingest_git_cochanges,
    ingest_git_contributors,
    ingest_git_hotspots,
    ingest_inheritance,
    ingest_lsp_definition,
    ingest_lsp_references,
    ingest_lsp_symbols,
    ingest_rg_matches,
    ingest_test_mapping,
)
from .analysis import CodeAnalyzer
from .disclosure import ProgressiveExplorer
from .model import CodeGraph

# Global graph storage (per session)
_graphs: dict[str, CodeGraph] = {}
_explorers: dict[str, ProgressiveExplorer] = {}


def _get_graph(graph_id: str) -> CodeGraph | None:
    """Get a graph by ID."""
    return _graphs.get(graph_id)


def _get_explorer(graph_id: str) -> ProgressiveExplorer | None:
    """Get or create an explorer for a graph."""
    if graph_id not in _explorers and graph_id in _graphs:
        _explorers[graph_id] = ProgressiveExplorer(_graphs[graph_id])
    return _explorers.get(graph_id)


def _json_response(data: dict[str, Any]) -> str:
    """Convert response to JSON string."""
    return json.dumps(data, indent=2, default=str)


@tool
def code_graph_create(
    graph_id: str,
    description: str = "",
) -> str:
    """Initialize an empty code graph for structural analysis of a codebase.

    USE THIS TOOL:
    - At the start of analysis, BEFORE running LSP/AST-grep tools
    - When you need to unify results from multiple discovery tools
    - When you want to run graph algorithms (hotspots, modules, coupling)

    DO NOT USE:
    - If a graph with this ID already exists (will overwrite it)
    - For simple single-file analysis (use LSP tools directly)

    The graph is stored in memory for the session. Populate it using:
    - code_graph_ingest_lsp: Add symbols, references, definitions from LSP
    - code_graph_ingest_astgrep: Add business logic patterns
    - code_graph_ingest_tests: Add test coverage relationships

    Args:
        graph_id: Unique identifier for this graph. Use descriptive names:
            - "main": Primary analysis graph for the whole codebase
            - "feature_auth": Graph focused on authentication code
            - "module_api": Graph for API layer only
        description: Human-readable description of what this graph represents.
            Helps when managing multiple graphs.

    Returns:
        JSON: {"status": "success", "graph_id": "...", "message": "..."}

    Output Size: ~100 bytes

    Workflow:
        1. code_graph_create("main")           # Initialize
        2. lsp_start(...) + lsp_document_symbols(...)  # Discover
        3. code_graph_ingest_lsp(...)          # Populate
        4. code_graph_analyze("main", "hotspots")  # Analyze
        5. code_graph_save("main", ".code-context/graph.json")  # Persist

    Example:
        code_graph_create("main", "Full codebase analysis")
        code_graph_create("backend", "Backend services only")
    """
    _graphs[graph_id] = CodeGraph()
    # Reset explorer for this graph
    _explorers.pop(graph_id, None)

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "description": description,
            "message": f"Created new code graph: {graph_id}",
        },
    )


@tool
def code_graph_ingest_lsp(  # noqa: C901
    graph_id: str,
    lsp_result: str,
    result_type: str,
    source_file: str = "",
    source_symbol: str = "",
) -> str:
    """Add LSP tool results to the code graph as nodes and edges.

    USE THIS TOOL:
    - After calling lsp_document_symbols to add function/class nodes
    - After calling lsp_references to add "references" edges (fan-in data)
    - After calling lsp_definition to add "calls" edges (call relationships)

    DO NOT USE:
    - Before calling code_graph_create (graph must exist first)
    - With invalid/empty LSP results (check LSP tool status first)

    Converts raw LSP data into graph structure:
    - "symbols" → Creates nodes for functions, classes, methods, variables
    - "references" → Creates edges showing where a symbol is used
    - "definition" → Creates edges showing what a symbol calls/uses

    Args:
        graph_id: ID of the target graph (must exist from code_graph_create)
        lsp_result: The raw JSON string output from an LSP tool.
            Pass the exact return value from lsp_document_symbols,
            lsp_references, or lsp_definition.
        result_type: Type of LSP result being ingested:
            - "symbols": From lsp_document_symbols. Creates nodes.
              REQUIRES source_file parameter.
            - "references": From lsp_references. Creates reference edges.
              REQUIRES source_symbol parameter (format: "file:name").
            - "definition": From lsp_definition. Creates call/import edges.
        source_file: Required for "symbols" type. The file path that was
            analyzed (e.g., "src/main.py"). Used to create node IDs.
        source_symbol: Required for "references" type. The symbol ID that
            references point TO (format: "src/main.py:my_function").

    Returns:
        JSON with ingestion results:
        {
            "status": "success",
            "nodes_added": 15,      # New nodes created
            "edges_added": 8,       # New edges created
            "total_nodes": 150,     # Graph totals
            "total_edges": 200
        }

    Output Size: ~200 bytes

    Common Errors:
        - "Graph not found": Call code_graph_create first
        - "source_file required": Must provide source_file for "symbols"
        - "source_symbol required": Must provide source_symbol for "references"
        - "Invalid JSON": LSP result is malformed

    Workflow Examples:

    Ingesting symbols (creates nodes):
        symbols = lsp_document_symbols(session_id, "src/api.py")
        code_graph_ingest_lsp("main", symbols, "symbols", source_file="src/api.py")

    Ingesting references (creates edges showing fan-in):
        refs = lsp_references(session_id, "src/api.py", 10, 5)
        code_graph_ingest_lsp("main", refs, "references",
                              source_symbol="src/api.py:handle_request")

    Ingesting definitions (creates call edges):
        defn = lsp_definition(session_id, "src/api.py", 15, 20)
        code_graph_ingest_lsp("main", defn, "definition")
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    try:
        result = json.loads(lsp_result)
    except json.JSONDecodeError as e:
        return _json_response({"status": "error", "message": f"Invalid JSON: {e}"})

    nodes_added = 0
    edges_added = 0

    if result_type == "symbols":
        if not source_file:
            return _json_response({"status": "error", "message": "source_file required for symbols"})
        nodes, edges = ingest_lsp_symbols(result, source_file)
        for node in nodes:
            if not graph.has_node(node.id):
                graph.add_node(node)
                nodes_added += 1
        for edge in edges:
            graph.add_edge(edge)
            edges_added += 1

    elif result_type == "references":
        if not source_symbol:
            return _json_response({"status": "error", "message": "source_symbol required for references"})
        edges = ingest_lsp_references(result, source_symbol)
        for edge in edges:
            graph.add_edge(edge)
            edges_added += 1

    elif result_type == "definition":
        # Extract source location from result
        from_file = result.get("file", source_file)
        from_line = result.get("position", {}).get("line", 0)
        edges = ingest_lsp_definition(result, from_file, from_line)
        for edge in edges:
            graph.add_edge(edge)
            edges_added += 1

    else:
        return _json_response({"status": "error", "message": f"Unknown result_type: {result_type}"})

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "result_type": result_type,
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "total_nodes": graph.node_count,
            "total_edges": graph.edge_count,
        },
    )


@tool
def code_graph_ingest_astgrep(
    graph_id: str,
    astgrep_result: str,
    result_type: str = "rule_pack",
) -> str:
    """Add AST-grep pattern matches to the graph as categorized business logic nodes.

    USE THIS TOOL:
    - After running astgrep_scan_rule_pack to add business logic patterns
    - After running astgrep_scan for custom pattern matches
    - When you want graph analysis to consider business logic categories

    DO NOT USE:
    - Before code_graph_create (graph must exist first)
    - With empty AST-grep results (check match count first)

    AST-grep matches become nodes with rich metadata:
    - category: "db", "auth", "http", "validation", etc.
    - severity: "error" (writes), "warning" (reads), "hint" (definitions)
    - rule_id: The specific pattern that matched

    This metadata enables category-based analysis:
    - code_graph_analyze("main", "category", category="db")
    - code_graph_explore("main", "category", category="auth")

    Args:
        graph_id: ID of the target graph (must exist from code_graph_create)
        astgrep_result: The raw JSON string output from astgrep_scan or
            astgrep_scan_rule_pack. Pass the exact return value.
        result_type: Source of the AST-grep result:
            - "rule_pack" (default): From astgrep_scan_rule_pack.
              Results include category, severity, rule_id metadata.
              Use this for business logic detection.
            - "scan": From astgrep_scan ad-hoc patterns.
              Results have pattern info but no category metadata.

    Returns:
        JSON with ingestion results:
        {
            "status": "success",
            "nodes_added": 25,
            "categories": ["db", "auth", "validation"],
            "total_nodes": 175
        }

    Output Size: ~300 bytes

    Common Errors:
        - "Graph not found": Call code_graph_create first
        - "Invalid JSON": AST-grep result is malformed

    Workflow Example:
        # Run rule pack for Python business logic
        matches = astgrep_scan_rule_pack("py_business_logic", repo_path)

        # Ingest into graph
        code_graph_ingest_astgrep("main", matches, "rule_pack")

        # Now analyze by category
        db_ops = code_graph_analyze("main", "category", category="db")
        auth_ops = code_graph_analyze("main", "category", category="auth")
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    try:
        result = json.loads(astgrep_result)
    except json.JSONDecodeError as e:
        return _json_response({"status": "error", "message": f"Invalid JSON: {e}"})

    nodes_added = 0
    categories: set[str] = set()

    if result_type == "rule_pack":
        nodes = ingest_astgrep_rule_pack(result)
    else:
        nodes = ingest_astgrep_matches(result)

    for node in nodes:
        if not graph.has_node(node.id):
            graph.add_node(node)
            nodes_added += 1
            if "category" in node.metadata:
                categories.add(node.metadata["category"])

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "result_type": result_type,
            "nodes_added": nodes_added,
            "categories": list(categories),
            "total_nodes": graph.node_count,
        },
    )


@tool
def code_graph_ingest_rg(
    graph_id: str,
    rg_result: str,
) -> str:
    """Add ripgrep search matches to the graph as preliminary nodes.

    USE THIS TOOL:
    - When LSP doesn't cover a language/pattern
    - For text-based patterns (SQL keywords, config values, comments)
    - As a fallback when semantic analysis isn't available

    DO NOT USE:
    - When LSP symbols are available (prefer code_graph_ingest_lsp)
    - For structural patterns (prefer code_graph_ingest_astgrep)

    Creates lightweight nodes from text matches. These nodes have:
    - file_path and line number
    - matched text content
    - No semantic type information (unlike LSP nodes)

    Ripgrep nodes are useful for:
    - Finding TODO/FIXME comments
    - Locating hardcoded values
    - Identifying SQL queries in strings

    Args:
        graph_id: ID of the target graph (must exist from code_graph_create)
        rg_result: The raw JSON string output from rg_search tool.
            Pass the exact return value.

    Returns:
        JSON: {"status": "success", "nodes_added": N, "total_nodes": M}

    Output Size: ~150 bytes

    Workflow Example:
        # Find all SQL queries
        sql_matches = rg_search("SELECT|INSERT|UPDATE|DELETE", repo_path)
        code_graph_ingest_rg("main", sql_matches)
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    try:
        result = json.loads(rg_result)
    except json.JSONDecodeError as e:
        return _json_response({"status": "error", "message": f"Invalid JSON: {e}"})

    nodes = ingest_rg_matches(result)
    nodes_added = 0

    for node in nodes:
        if not graph.has_node(node.id):
            graph.add_node(node)
            nodes_added += 1

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "nodes_added": nodes_added,
            "total_nodes": graph.node_count,
        },
    )


@tool
def code_graph_ingest_inheritance(
    graph_id: str,
    hover_content: str,
    class_node_id: str,
    file_path: str,
) -> str:
    """Add class inheritance/implementation edges from LSP hover information.

    USE THIS TOOL:
    - After lsp_hover on a class to capture extends/implements relationships
    - When building class hierarchy for OOP codebases
    - In DEEP mode for comprehensive type analysis

    DO NOT USE:
    - On non-class symbols (functions, variables)
    - Without first creating the class node via code_graph_ingest_lsp

    Parses class signatures to create edges:
    - "inherits" edges: class Foo extends Bar → Foo --inherits--> Bar
    - "implements" edges: class Foo implements IBar → Foo --implements--> IBar

    Works with common patterns:
    - TypeScript/JavaScript: extends, implements
    - Python: class Foo(Bar, Baz)
    - Java: extends, implements

    Args:
        graph_id: ID of the target graph (must exist from code_graph_create)
        hover_content: The markdown/text content from lsp_hover result.
            Extract the "value" field from the hover response.
            Example: "class UserService extends BaseService implements IUserService"
        class_node_id: The node ID of the class in the graph.
            Format: "file_path:ClassName" (e.g., "src/services/user.ts:UserService")
            Must match the ID created by code_graph_ingest_lsp.
        file_path: Path to the file containing this class.
            Used to resolve base class locations.

    Returns:
        JSON: {"status": "success", "edges_added": N, "edge_types": ["inherits", "implements"]}

    Output Size: ~200 bytes

    Workflow Example:
        # Get class symbols
        symbols = lsp_document_symbols(session_id, "src/user.ts")
        code_graph_ingest_lsp("main", symbols, "symbols", source_file="src/user.ts")

        # For each class, get hover info and ingest inheritance
        hover = lsp_hover(session_id, "src/user.ts", class_line, 0)
        hover_content = hover["hover"]["contents"]["value"]
        code_graph_ingest_inheritance("main", hover_content,
                                      "src/user.ts:UserService", "src/user.ts")
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    edges = ingest_inheritance(hover_content, class_node_id, file_path)
    edges_added = 0

    for edge in edges:
        graph.add_edge(edge)
        edges_added += 1

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "edges_added": edges_added,
            "edge_types": ["inherits", "implements"],
            "total_edges": graph.edge_count,
        },
    )


@tool
def code_graph_ingest_tests(
    graph_id: str,
    test_files: str,
    production_files: str,
) -> str:
    """Add test-to-production file mappings as "tests" edges in the graph.

    USE THIS TOOL:
    - After identifying test files (via rg_search for test patterns)
    - To enable test coverage analysis on business logic
    - To find untested hotspots in the codebase

    DO NOT USE:
    - With unfiltered file lists (only include actual test files)
    - Before adding production file nodes to the graph

    Creates "tests" edges based on naming convention matching:
    - test_foo.py → foo.py
    - foo.test.ts → foo.ts
    - FooTest.java → Foo.java
    - __tests__/foo.test.js → src/foo.js

    These edges enable:
    - Finding untested business logic (nodes without incoming test edges)
    - Understanding test coverage per module
    - Prioritizing testing efforts on hotspots

    Args:
        graph_id: ID of the target graph (must exist from code_graph_create)
        test_files: JSON array of test file paths as a string.
            Example: '["tests/test_user.py", "tests/test_auth.py"]'
            Obtain from rg_search or file manifest filtering.
        production_files: JSON array of production file paths as a string.
            Example: '["src/user.py", "src/auth.py"]'
            Should include all files you want to map tests to.

    Returns:
        JSON: {"status": "success", "edges_added": N, "total_edges": M}

    Output Size: ~150 bytes

    Workflow Example:
        # Find test files
        test_matches = rg_search("def test_|it\\(|describe\\(", repo_path)
        test_files = extract_unique_files(test_matches)

        # Get production files from manifest
        prod_files = filter_non_test_files(manifest)

        # Create test mapping edges
        code_graph_ingest_tests("main",
                                json.dumps(test_files),
                                json.dumps(prod_files))

        # Find untested hotspots
        hotspots = code_graph_analyze("main", "hotspots", top_k=10)
        # Check which have no incoming "tests" edges
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    try:
        tests = json.loads(test_files)
        prods = json.loads(production_files)
    except json.JSONDecodeError as e:
        return _json_response({"status": "error", "message": f"Invalid JSON: {e}"})

    edges = ingest_test_mapping(tests, prods)
    edges_added = 0

    for edge in edges:
        graph.add_edge(edge)
        edges_added += 1

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "edges_added": edges_added,
            "total_edges": graph.edge_count,
        },
    )


@tool
def code_graph_analyze(  # noqa: C901
    graph_id: str,
    analysis_type: str,
    top_k: int = 10,
    node_a: str = "",
    node_b: str = "",
    resolution: float = 1.0,
    category: str = "",
) -> str:
    """Run graph algorithms to surface structural insights about the codebase.

    USE THIS TOOL:
    - After populating graph with code_graph_ingest_* tools
    - To find important code that isn't obvious from file names
    - To understand code relationships and architecture

    DO NOT USE:
    - On an empty graph (ingest data first)
    - For simple lookups (use code_graph_explore instead)

    Analysis types provide different perspectives:

    **Centrality (finds important code):**
    - "hotspots": Betweenness centrality. Finds bottleneck code that many
      paths go through. High score = integration point, likely to cause
      cascading changes. Use for: risk assessment, refactoring targets.
    - "foundations": PageRank. Finds core infrastructure that other
      important code depends on. High score = foundational code.
      Use for: understanding dependencies, documentation priority.
    - "entry_points": Nodes with no incoming edges but outgoing calls.
      These start execution flows. Use for: understanding app structure.

    **Clustering (finds groupings):**
    - "modules": Louvain community detection. Finds densely connected
      groups = logical modules/layers. Use for: architecture diagrams,
      understanding boundaries.

    **Relationships (between specific nodes):**
    - "coupling": Measures how tightly two nodes are connected.
      Use for: understanding change impact, identifying tight coupling.
    - "similar": Personalized PageRank from a node. Finds related code.
      Use for: understanding a node's neighborhood.
    - "dependencies": BFS from a node. Shows what it depends on.
      Use for: understanding impact of changes.

    **Filtering:**
    - "category": Finds all nodes in a business logic category.
      Use for: focused analysis on db/auth/validation/etc.

    Args:
        graph_id: ID of the graph to analyze (must have data from ingestion)
        analysis_type: Algorithm to run. One of:
            - "hotspots": Returns ranked list by betweenness score
            - "foundations": Returns ranked list by PageRank score
            - "entry_points": Returns list of entry point nodes
            - "modules": Returns list of detected modules with members
            - "coupling": Returns coupling metrics (requires node_a, node_b)
            - "similar": Returns similar nodes (requires node_a)
            - "category": Returns nodes in category (requires category)
            - "dependencies": Returns dependency chain (requires node_a)
            - "trust": TrustRank-based foundations (noise-resistant PageRank from entry points)
            - "triangles": Find tightly-coupled code triads
        top_k: Maximum results for ranked analyses (hotspots, foundations,
            similar). Default 10. Use 20-30 for comprehensive analysis.
        node_a: Required for "coupling", "similar", "dependencies".
            Node ID format: "file_path:symbol_name"
        node_b: Required for "coupling" analysis. Second node to compare.
        resolution: For "modules" only. Controls cluster granularity:
            - < 1.0: Fewer, larger clusters (e.g., 0.5 for high-level layers)
            - = 1.0: Default clustering
            - > 1.0: More, smaller clusters (e.g., 1.5 for fine-grained)
        category: Required for "category" analysis. Category name from
            AST-grep rule packs: "db", "auth", "http", "validation", etc.

    Returns:
        JSON with analysis results. Format varies by type:

        hotspots/foundations:
        {"results": [{"id": "...", "score": 0.85, "name": "...", ...}]}

        modules:
        {"module_count": 5, "results": [
            {"module_id": 0, "size": 15, "key_nodes": [...], "cohesion": 0.8}
        ]}

        coupling:
        {"results": {"coupling": 2.5, "shared_neighbors": 3, "path_length": 2}}

    Output Size: 1-10KB depending on top_k and analysis type

    Workflow Examples:

    Find bottleneck code:
        hotspots = code_graph_analyze("main", "hotspots", top_k=15)
        # Results ranked by betweenness - top items are integration points

    Detect architecture layers:
        modules = code_graph_analyze("main", "modules", resolution=0.8)
        # Each module is a logical grouping - name based on key_nodes

    Understand coupling:
        coupling = code_graph_analyze("main", "coupling",
                                       node_a="src/api.py:handler",
                                       node_b="src/db.py:repository")
        # High coupling score = tightly connected, changes propagate

    Find all database operations:
        db_ops = code_graph_analyze("main", "category", category="db")
        # Returns all nodes tagged as "db" from AST-grep ingestion
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    analyzer = CodeAnalyzer(graph)

    if analysis_type == "hotspots":
        results = analyzer.find_hotspots(top_k)
        return _json_response({"status": "success", "analysis": "hotspots", "results": results})

    if analysis_type == "foundations":
        results = analyzer.find_foundations(top_k)
        return _json_response({"status": "success", "analysis": "foundations", "results": results})

    if analysis_type == "entry_points":
        results = analyzer.find_entry_points()
        return _json_response({"status": "success", "analysis": "entry_points", "results": results})

    if analysis_type == "modules":
        results = analyzer.detect_modules(resolution)
        return _json_response(
            {"status": "success", "analysis": "modules", "module_count": len(results), "results": results},
        )

    if analysis_type == "coupling":
        if not node_a or not node_b:
            return _json_response({"status": "error", "message": "node_a and node_b required for coupling"})
        results = analyzer.calculate_coupling(node_a, node_b)
        return _json_response({"status": "success", "analysis": "coupling", "results": results})

    if analysis_type == "similar":
        if not node_a:
            return _json_response({"status": "error", "message": "node_a required for similar analysis"})
        results = analyzer.get_similar_nodes(node_a, top_k)
        return _json_response({"status": "success", "analysis": "similar", "results": results})

    if analysis_type == "category":
        if not category:
            return _json_response({"status": "error", "message": "category required for category analysis"})
        results = analyzer.find_clusters_by_category(category)
        return _json_response({"status": "success", "analysis": "category", "category": category, "results": results})

    if analysis_type == "dependencies":
        if not node_a:
            return _json_response({"status": "error", "message": "node_a required for dependencies"})
        direction = "outgoing"  # What does this node depend on
        results = analyzer.get_dependency_chain(node_a, direction)
        return _json_response({"status": "success", "analysis": "dependencies", "results": results})

    if analysis_type == "trust":
        results = analyzer.find_trusted_foundations(top_k=top_k)
        return _json_response({"status": "success", "analysis": "trust", "results": results})

    if analysis_type == "triangles":
        results = analyzer.find_triangles(top_k=top_k)
        return _json_response({"status": "success", "analysis": "triangles", "results": results})

    return _json_response({"status": "error", "message": f"Unknown analysis_type: {analysis_type}"})


@tool
def code_graph_explore(  # noqa: C901
    graph_id: str,
    action: str,
    node_id: str = "",
    module_id: int = -1,
    target_node: str = "",
    depth: int = 1,
    category: str = "",
) -> str:
    """Progressively explore the code graph to build context incrementally.

    USE THIS TOOL:
    - ALWAYS start with "overview" action first
    - When you need to understand the codebase step by step
    - To get suggestions on where to explore next
    - To track what you've already explored

    DO NOT USE:
    - For running analysis algorithms (use code_graph_analyze instead)
    - On an empty graph (ingest data first)

    Progressive disclosure pattern:
    1. "overview" → Get entry points, hotspots, modules, foundations
    2. Pick interesting nodes from overview
    3. "expand_node" → See neighbors and relationships
    4. Repeat until sufficient context is gathered

    The explorer tracks visited nodes and suggests what to explore next.

    Actions:

    **Starting point:**
    - "overview": Returns high-level structure. Includes:
      - entry_points: Where execution starts
      - hotspots: Bottleneck code (top 5)
      - modules: Detected clusters with key nodes
      - foundations: Core infrastructure (top 5)
      Always start here to orient yourself.

    **Drill-down:**
    - "expand_node": BFS expansion from a node. See immediate neighbors
      and their relationships. Good for understanding a specific area.
    - "expand_module": Deep-dive into a detected module. Shows internal
      structure and external connections.
    - "category": Explore all nodes in a business logic category.
      Groups results by file.

    **Navigation:**
    - "path": Find shortest path between two nodes. Useful for
      understanding how components connect.
    - "status": Check exploration coverage (% of nodes visited).
    - "reset": Clear exploration state to start fresh.

    Args:
        graph_id: ID of the graph to explore (must have data from ingestion)
        action: Exploration action. One of:
            - "overview": No additional params needed
            - "expand_node": Requires node_id, optional depth
            - "expand_module": Requires module_id (from overview/modules analysis)
            - "path": Requires node_id (source) and target_node
            - "category": Requires category (e.g., "db", "auth")
            - "status": No additional params
            - "reset": No additional params
        node_id: For "expand_node": Node ID to expand from.
            For "path": Source node. Format: "file_path:symbol_name"
        module_id: For "expand_module": Module ID from detect_modules results.
            Typically 0, 1, 2, etc. from the overview.
        target_node: For "path": Destination node ID.
        depth: For "expand_node": How many hops to expand.
            - depth=1: Direct neighbors only (fast, focused)
            - depth=2: Neighbors of neighbors (broader context)
            - depth=3+: Rarely needed, can be large
        category: For "category": Business logic category name.
            Values from AST-grep: "db", "auth", "http", "validation", etc.

    Returns:
        JSON with exploration results. Always includes "explored_count".

        overview:
        {
            "entry_points": [...],
            "hotspots": [...],
            "modules": [{"module_id": 0, "size": 15, "key_nodes": [...]}],
            "foundations": [...],
            "explored_count": 25
        }

        expand_node:
        {
            "center": "src/api.py:handler",
            "discovered_nodes": [...],
            "edges": [...],
            "suggested_next": [...],  # What to explore next
            "explored_count": 40
        }

    Output Size: 2-20KB depending on action and graph size

    Workflow Example:

    # 1. Start with overview
    overview = code_graph_explore("main", "overview")
    # Look at entry_points and hotspots

    # 2. Expand from interesting hotspot
    details = code_graph_explore("main", "expand_node",
                                  node_id=overview["hotspots"][0]["id"],
                                  depth=2)
    # See neighbors and suggested_next

    # 3. Explore a module
    module_details = code_graph_explore("main", "expand_module", module_id=0)
    # See internal structure and external connections

    # 4. Check coverage
    status = code_graph_explore("main", "status")
    # coverage_percent shows how much of graph was explored
    """
    explorer = _get_explorer(graph_id)
    if explorer is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    if action == "overview":
        results = explorer.get_overview()
        return _json_response({"status": "success", "action": "overview", **results})

    if action == "expand_node":
        if not node_id:
            return _json_response({"status": "error", "message": "node_id required for expand_node"})
        results = explorer.expand_node(node_id, depth)
        return _json_response({"status": "success", "action": "expand_node", **results})

    if action == "expand_module":
        if module_id < 0:
            return _json_response({"status": "error", "message": "module_id required for expand_module"})
        results = explorer.expand_module(module_id)
        return _json_response({"status": "success", "action": "expand_module", **results})

    if action == "path":
        if not node_id or not target_node:
            return _json_response({"status": "error", "message": "node_id and target_node required for path"})
        results = explorer.get_path_between(node_id, target_node)
        return _json_response({"status": "success", "action": "path", **results})

    if action == "category":
        if not category:
            return _json_response({"status": "error", "message": "category required for category exploration"})
        results = explorer.explore_category(category)
        return _json_response({"status": "success", "action": "category", **results})

    if action == "status":
        results = explorer.get_exploration_status()
        return _json_response({"status": "success", "action": "status", **results})

    if action == "reset":
        explorer.reset_exploration()
        return _json_response({"status": "success", "action": "reset", "message": "Exploration state reset"})

    return _json_response({"status": "error", "message": f"Unknown action: {action}"})


@tool
def code_graph_export(
    graph_id: str,
    format: str = "json",
    include_metadata: bool = True,
    max_nodes: int = 100,
) -> str:
    """Export the code graph for visualization or external analysis.

    USE THIS TOOL:
    - To generate Mermaid diagrams for CONTEXT.md architecture section
    - To save graph data for external visualization tools
    - After analysis, to capture the graph structure

    DO NOT USE:
    - For persistence (use code_graph_save instead)
    - On empty graphs (ingest data first)

    Export formats:

    **"mermaid"** (recommended for documentation):
    Generates Mermaid diagram syntax that can be embedded in markdown.
    - Selects top nodes by degree (most connected = most important)
    - Uses shapes based on node type:
      - [name]: Classes (rectangles)
      - (name): Functions/methods (rounded)
      - [[name]]: Files (stadium shape)
    - Edge styles by relationship:
      - --> : calls
      - -.-> : imports
      - ==> : inherits

    **"json"** (for external tools):
    NetworkX node-link format. Can be loaded into other graph tools.

    Args:
        graph_id: ID of the graph to export (must exist)
        format: Export format:
            - "mermaid": Mermaid diagram syntax (for markdown embedding)
            - "json": NetworkX node-link JSON (for external tools)
        include_metadata: For "json" format only. Whether to include
            node/edge metadata (file_path, line numbers, etc.).
            Set False for smaller output.
        max_nodes: For "mermaid" format only. Maximum nodes to include.
            Mermaid diagrams become unreadable with too many nodes.
            Recommended: 15 for CONTEXT.md, up to 50 for detailed diagrams.
            Nodes are selected by degree (most connected first).

    Returns:
        For "mermaid":
        {
            "status": "success",
            "format": "mermaid",
            "diagram": "graph TD\\n    node1[Name] --> node2..."
        }

        For "json":
        {
            "status": "success",
            "format": "json",
            "graph": {"nodes": [...], "links": [...]}
        }

    Output Size:
        - mermaid: 1-5KB (limited by max_nodes)
        - json: 10-500KB (depends on graph size)

    Workflow Example:

    # Export for CONTEXT.md architecture diagram
    result = code_graph_export("main", format="mermaid", max_nodes=15)
    mermaid_code = result["diagram"]
    # Embed in markdown:
    # ```mermaid
    # {mermaid_code}
    # ```

    # Export for external visualization
    result = code_graph_export("main", format="json", include_metadata=True)
    # Use with Gephi, D3.js, etc.
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    if format == "json":
        data = graph.to_node_link_data()
        if not include_metadata:
            # Strip metadata
            for node in data.get("nodes", []):
                node.pop("metadata", None)
            for link in data.get("links", []):
                link.pop("metadata", None)
        return _json_response({"status": "success", "format": "json", "graph": data})

    if format == "mermaid":
        mermaid = _export_mermaid(graph, max_nodes)
        return _json_response({"status": "success", "format": "mermaid", "diagram": mermaid})

    return _json_response({"status": "error", "message": f"Unknown format: {format}"})


def _export_mermaid(graph: CodeGraph, max_nodes: int = 100) -> str:
    """Export graph as Mermaid diagram.

    Args:
        graph: The CodeGraph to export
        max_nodes: Maximum nodes to include

    Returns:
        Mermaid diagram string
    """
    lines = ["graph TD"]

    # Get top nodes by degree
    view = graph.get_view()
    degrees = dict(view.degree())
    top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:max_nodes]
    included_nodes = {n for n, _ in top_nodes}

    # Add nodes with labels
    for node_id, _ in top_nodes:
        data = graph.get_node_data(node_id) or {}
        name = data.get("name", node_id.split(":")[-1])
        node_type = data.get("node_type", "unknown")

        # Sanitize for Mermaid
        safe_id = node_id.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")
        safe_name = name.replace('"', "'").replace("(", "[").replace(")", "]")[:30]

        # Shape based on type
        if node_type == "class":
            lines.append(f'    {safe_id}["{safe_name}"]')
        elif node_type in ("function", "method"):
            lines.append(f'    {safe_id}("{safe_name}")')
        elif node_type == "file":
            lines.append(f'    {safe_id}[["{safe_name}"]]')
        else:
            lines.append(f'    {safe_id}["{safe_name}"]')

    # Add edges (only between included nodes)
    for u, v, data in graph.edges(data=True):
        if u in included_nodes and v in included_nodes:
            safe_u = u.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")
            safe_v = v.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")
            edge_type = data.get("edge_type", "")

            if edge_type == "calls":
                lines.append(f"    {safe_u} --> {safe_v}")
            elif edge_type == "imports":
                lines.append(f"    {safe_u} -.-> {safe_v}")
            elif edge_type == "inherits":
                lines.append(f"    {safe_u} ==> {safe_v}")
            else:
                lines.append(f"    {safe_u} --> {safe_v}")

    return "\n".join(lines)


@tool
def code_graph_save(
    graph_id: str,
    file_path: str,
) -> str:
    """Persist the code graph to disk for reuse in future sessions.

    USE THIS TOOL:
    - After completing graph analysis (DEEP mode)
    - When you want to preserve analysis results
    - Before ending a session with valuable graph data

    DO NOT USE:
    - For exporting to visualization formats (use code_graph_export)
    - On empty graphs (waste of disk space)

    Saves the complete graph structure including:
    - All nodes with metadata (file_path, line numbers, categories)
    - All edges with types (calls, references, imports, inherits)
    - All analysis-relevant data

    Saved graphs can be reloaded with code_graph_load, avoiding
    the need to re-run LSP/AST-grep tools.

    Args:
        graph_id: ID of the graph to save (must exist)
        file_path: Destination file path. Recommended locations:
            - ".code-context/code_graph.json": Standard location for main graph
            - ".code-context/{name}_graph.json": For named/scoped graphs
            Parent directories are created automatically.

    Returns:
        JSON: {
            "status": "success",
            "graph_id": "main",
            "path": ".code-context/code_graph.json",
            "nodes": 150,
            "edges": 200
        }

    Output Size: ~100 bytes (file size varies: 10KB-1MB)

    Common Errors:
        - "Graph not found": Graph ID doesn't exist
        - "Save failed": File system error (permissions, disk full)

    Workflow Example:

    # After comprehensive analysis in DEEP mode
    code_graph_create("main")
    # ... ingest LSP, AST-grep data ...
    # ... run analysis ...

    # Save for future sessions
    code_graph_save("main", ".code-context/code_graph.json")

    # In future session:
    code_graph_load("main", ".code-context/code_graph.json")
    # Graph restored with all nodes/edges
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    try:
        data = graph.to_node_link_data()
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
    except (OSError, ValueError, TypeError) as e:
        return _json_response({"status": "error", "message": f"Save failed: {e}"})

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "path": str(path),
            "nodes": graph.node_count,
            "edges": graph.edge_count,
        },
    )


@tool
def code_graph_load(
    graph_id: str,
    file_path: str,
) -> str:
    """Load a previously saved code graph from disk.

    USE THIS TOOL:
    - At the start of a session if .code-context/code_graph.json exists
    - To resume analysis from a previous session
    - To skip re-running LSP/AST-grep data collection

    DO NOT USE:
    - If graph file doesn't exist (check with file system first)
    - When you need fresh analysis (create new graph instead)

    Loading a saved graph restores:
    - All nodes with their metadata
    - All edges with their types
    - Ready for immediate analysis (code_graph_analyze, code_graph_explore)

    Note: Loading replaces any existing graph with the same ID.
    The explorer state is reset (tracked exploration cleared).

    Args:
        graph_id: ID to assign to the loaded graph. Use:
            - "main": For the primary codebase graph
            - Descriptive names for scoped graphs
        file_path: Path to the saved graph file.
            Standard location: ".code-context/code_graph.json"

    Returns:
        JSON: {
            "status": "success",
            "graph_id": "main",
            "path": ".code-context/code_graph.json",
            "nodes": 150,
            "edges": 200
        }

    Output Size: ~100 bytes

    Common Errors:
        - "Load failed": File not found or invalid JSON

    Workflow Example:

    # Check if saved graph exists
    # If .code-context/code_graph.json exists:
    code_graph_load("main", ".code-context/code_graph.json")

    # Graph is ready for analysis
    hotspots = code_graph_analyze("main", "hotspots")
    overview = code_graph_explore("main", "overview")

    # No need to re-run lsp_* or astgrep_* tools!
    """
    try:
        path = Path(file_path)
        data = json.loads(path.read_text())
        graph = CodeGraph.from_node_link_data(data)
        _graphs[graph_id] = graph
        # Reset explorer
        _explorers.pop(graph_id, None)
    except (OSError, ValueError, TypeError, KeyError) as e:
        return _json_response({"status": "error", "message": f"Load failed: {e}"})

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "path": str(path),
            "nodes": graph.node_count,
            "edges": graph.edge_count,
        },
    )


@tool
def code_graph_stats(
    graph_id: str,
) -> str:
    """Get summary statistics about a code graph.

    USE THIS TOOL:
    - To verify graph was populated correctly after ingestion
    - To understand graph composition before analysis
    - For the completion signal (graph node/edge counts)

    DO NOT USE:
    - For detailed analysis (use code_graph_analyze)
    - For exploration (use code_graph_explore)

    Returns counts broken down by type:
    - Nodes by type: function, class, method, variable, pattern_match
    - Edges by type: calls, references, imports, inherits, tests

    This helps verify:
    - LSP ingestion worked (function/class nodes exist)
    - AST-grep ingestion worked (pattern_match nodes exist)
    - Reference tracking worked (references edges exist)
    - Test mapping worked (tests edges exist)

    Args:
        graph_id: ID of the graph to get stats for (must exist)

    Returns:
        JSON: {
            "status": "success",
            "graph_id": "main",
            "total_nodes": 150,
            "total_edges": 200,
            "nodes_by_type": {
                "function": 80,
                "class": 20,
                "method": 40,
                "pattern_match": 10
            },
            "edges_by_type": {
                "calls": 100,
                "references": 60,
                "imports": 30,
                "tests": 10
            }
        }

    Output Size: ~300 bytes

    Workflow Example:

    # After ingestion, verify graph state
    stats = code_graph_stats("main")

    # Check ingestion worked
    if stats["nodes_by_type"]["function"] == 0:
        # LSP symbols not ingested properly

    if stats["edges_by_type"]["references"] == 0:
        # LSP references not ingested

    # Use in completion signal
    # Graph: {stats["total_nodes"]} nodes, {stats["total_edges"]} edges
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    # Count nodes by type
    node_types: dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        ntype = data.get("node_type", "unknown")
        node_types[ntype] = node_types.get(ntype, 0) + 1

    # Count edges by type
    edge_types: dict[str, int] = {}
    for _, _, data in graph.edges(data=True):
        etype = data.get("edge_type", "unknown")
        edge_types[etype] = edge_types.get(etype, 0) + 1

    return _json_response(
        {
            "status": "success",
            "graph_id": graph_id,
            "total_nodes": graph.node_count,
            "total_edges": graph.edge_count,
            "nodes_by_type": node_types,
            "edges_by_type": edge_types,
        },
    )


@tool
def code_graph_ingest_git(
    graph_id: str,
    git_result: str,
    result_type: str,
    source_file: str = "",
    min_percentage: float = 20.0,
) -> str:
    """Add git history data to the code graph as nodes, edges, or metadata.

    USE THIS TOOL:
    - After calling git_hotspots to add churn metadata to FILE nodes
    - After calling git_files_changed_together to add COCHANGES edges
    - After calling git_contributors or git_blame_summary to add ownership metadata

    DO NOT USE:
    - Before code_graph_create (graph must exist first)
    - With error-status git results

    Args:
        graph_id: ID of the target graph (must exist from code_graph_create)
        git_result: The raw JSON string output from a git tool.
            Pass the exact return value from git_hotspots,
            git_files_changed_together, git_contributors, or git_blame_summary.
        result_type: Type of git result being ingested:
            - "hotspots": From git_hotspots. Creates/updates FILE nodes with churn metadata.
            - "cochanges": From git_files_changed_together. Creates COCHANGES edges.
              Uses min_percentage to filter low-coupling pairs.
            - "contributors": From git_contributors or git_blame_summary.
              Returns ownership metadata dict.
        source_file: For "contributors" type. If provided and the node exists,
            attaches contributor metadata to the FILE node at this path.
        min_percentage: For "cochanges" type. Minimum co-change percentage
            to create an edge (default 20.0). Lower = more edges.

    Returns:
        JSON with ingestion results varying by type.

    Output Size: ~200 bytes

    Workflow Examples:

    Ingesting hotspots (creates/updates FILE nodes):
        hotspots = git_hotspots(repo_path, limit=30)
        code_graph_ingest_git("main", hotspots, "hotspots")

    Ingesting co-changes (creates COCHANGES edges):
        coupling = git_files_changed_together(repo_path, "src/auth.py")
        code_graph_ingest_git("main", coupling, "cochanges", min_percentage=15.0)

    Ingesting contributors (returns metadata):
        blame = git_blame_summary(repo_path, "src/auth.py")
        code_graph_ingest_git("main", blame, "contributors", source_file="src/auth.py")
    """
    graph = _get_graph(graph_id)
    if graph is None:
        return _json_response({"status": "error", "message": f"Graph not found: {graph_id}"})

    try:
        result = json.loads(git_result)
    except json.JSONDecodeError as e:
        return _json_response({"status": "error", "message": f"Invalid JSON: {e}"})

    if result_type == "hotspots":
        nodes = ingest_git_hotspots(result)
        nodes_added = 0
        nodes_updated = 0
        for node in nodes:
            if graph.has_node(node.id):
                # Merge churn metadata into existing node
                existing = graph._graph.nodes[node.id]
                existing.setdefault("metadata", {}).update(node.metadata)
                nodes_updated += 1
            else:
                graph.add_node(node)
                nodes_added += 1
        return _json_response(
            {
                "status": "success",
                "graph_id": graph_id,
                "result_type": "hotspots",
                "nodes_added": nodes_added,
                "nodes_updated": nodes_updated,
                "total_nodes": graph.node_count,
            },
        )

    if result_type == "cochanges":
        edges = ingest_git_cochanges(result, min_percentage=min_percentage)
        edges_added = 0
        for edge in edges:
            graph.add_edge(edge)
            edges_added += 1
        return _json_response(
            {
                "status": "success",
                "graph_id": graph_id,
                "result_type": "cochanges",
                "edges_added": edges_added,
                "total_edges": graph.edge_count,
            },
        )

    if result_type == "contributors":
        metadata = ingest_git_contributors(result)
        if source_file and graph.has_node(source_file):
            graph._graph.nodes[source_file].setdefault("metadata", {}).update(metadata)
        return _json_response(
            {
                "status": "success",
                "graph_id": graph_id,
                "result_type": "contributors",
                "contributor_count": metadata.get("contributor_count", 0),
            },
        )

    return _json_response({"status": "error", "message": f"Unknown result_type: {result_type}"})
