"""Code graph analysis package.

Provides tools for building and analyzing code graphs using NetworkX:
- Graph construction from LSP, AST-grep, and ripgrep results
- Analysis algorithms (clustering, centrality, traversal)
- Progressive disclosure for AI context generation
- Export to Mermaid and JSON formats
"""

from .analysis import CodeAnalyzer
from .disclosure import ProgressiveExplorer
from .model import CodeEdge, CodeGraph, CodeNode, EdgeType, NodeType
from .tools import (
    code_graph_analyze,
    code_graph_create,
    code_graph_explore,
    code_graph_export,
    code_graph_ingest_astgrep,
    code_graph_ingest_clones,
    code_graph_ingest_git,
    code_graph_ingest_inheritance,
    code_graph_ingest_lsp,
    code_graph_ingest_rg,
    code_graph_ingest_tests,
    code_graph_load,
    code_graph_save,
    code_graph_stats,
)

__all__ = [
    # Model
    "NodeType",
    "EdgeType",
    "CodeNode",
    "CodeEdge",
    "CodeGraph",
    # Analysis
    "CodeAnalyzer",
    # Progressive disclosure
    "ProgressiveExplorer",
    # Tools (strands @tool functions)
    "code_graph_create",
    "code_graph_ingest_lsp",
    "code_graph_ingest_astgrep",
    "code_graph_ingest_rg",
    "code_graph_ingest_clones",
    "code_graph_ingest_git",
    "code_graph_ingest_inheritance",
    "code_graph_ingest_tests",
    "code_graph_analyze",
    "code_graph_explore",
    "code_graph_export",
    "code_graph_save",
    "code_graph_load",
    "code_graph_stats",
]
