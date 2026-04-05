"""Load and parse .code-context/ artifacts into a unified data container."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003 — used at runtime in dataclass field
from typing import Any

from loguru import logger


@dataclass
class DashboardCache:
    """Pre-computed aggregations cached at load time."""

    # Degree centrality (computed from edges)
    degree_df: Any = None  # pl.DataFrame: id, name, node_type, file_path, in_degree, out_degree, total_degree

    # Distribution counts
    node_type_counts: Any = None  # pl.DataFrame: node_type, count
    edge_type_counts: Any = None  # pl.DataFrame: edge_type, count

    # Community assignments (cached Louvain result)
    community_assignments: Any = None  # pl.DataFrame: id, community_id

    # DuckDB connection with registered frames
    duckdb_con: Any = None  # duckdb.DuckDBPyConnection

    def query(self, sql: str) -> Any:
        """Execute a DuckDB SQL query against registered DataFrames.

        Args:
            sql: SQL query string. Tables available: nodes, edges, degree, communities.

        Returns:
            polars DataFrame with query results.
        """
        if self.duckdb_con is None:
            msg = "DuckDB connection not initialized"
            raise RuntimeError(msg)
        return self.duckdb_con.sql(sql).pl()


@dataclass
class DashboardData:
    """Container for all dashboard data sources."""

    agent_dir: Path

    # Graph data (NetworkX MultiDiGraph)
    graph: Any | None = None  # CodeGraph instance
    graph_raw: dict[str, Any] = field(default_factory=dict)

    # Analysis result
    analysis_result: dict[str, Any] = field(default_factory=dict)

    # Heuristic summary (NEW — not consumed by old React UI)
    heuristic_summary: dict[str, Any] = field(default_factory=dict)

    # Markdown content
    narrative: str = ""
    bundles: dict[str, str] = field(default_factory=dict)
    signatures: str = ""

    # File manifest
    files_list: str = ""

    # Polars DataFrames (populated from parquet or JSON fallback)
    nodes_df: Any = None  # pl.DataFrame
    edges_df: Any = None  # pl.DataFrame

    # Pre-computed cache
    cache: DashboardCache = field(default_factory=DashboardCache)


def _build_graph_from_polars(nodes_df: Any, edges_df: Any) -> Any:
    """Reconstruct a CodeGraph from polars DataFrames.

    Args:
        nodes_df: polars DataFrame with node data (must have 'id' column).
        edges_df: polars DataFrame with edge data (must have 'source', 'target' columns).

    Returns:
        CodeGraph instance populated from the DataFrames.
    """
    from code_context_agent.tools.graph.model import CodeGraph

    graph = CodeGraph()

    # Add nodes
    for row in nodes_df.iter_rows(named=True):
        node_id = row["id"]
        attrs = {k: v for k, v in row.items() if k not in {"id", "metadata_json"} and v is not None}
        graph._graph.add_node(node_id, **attrs)

    # Add edges
    for row in edges_df.iter_rows(named=True):
        source = row.get("source")
        target = row.get("target")
        if source and target:
            edge_type = row.get("edge_type", "unknown")
            attrs = {k: v for k, v in row.items() if k not in ("source", "target", "metadata_json") and v is not None}
            graph._graph.add_edge(source, target, key=edge_type, **attrs)

    return graph


def _build_cache(data: DashboardData) -> None:
    """Pre-compute aggregations and register DuckDB tables.

    Populates ``data.cache`` with degree centrality, type distribution counts,
    community assignments (Louvain), and a DuckDB connection for ad-hoc SQL.

    Args:
        data: DashboardData instance with nodes_df and edges_df populated.
    """
    try:
        import duckdb  # ty: ignore[unresolved-import]
        import polars as pl  # ty: ignore[unresolved-import]
    except ImportError:
        return  # polars/duckdb not installed

    if data.nodes_df is None or data.edges_df is None:
        return

    cache = data.cache
    nodes = data.nodes_df
    edges = data.edges_df

    # --- Degree centrality ---
    if len(edges) > 0 and "source" in edges.columns:
        out_deg = edges.group_by("source").len().rename({"source": "id", "len": "out_degree"})
    else:
        out_deg = pl.DataFrame({"id": [], "out_degree": []}, schema={"id": pl.Utf8, "out_degree": pl.UInt32})

    if len(edges) > 0 and "target" in edges.columns:
        in_deg = edges.group_by("target").len().rename({"target": "id", "len": "in_degree"})
    else:
        in_deg = pl.DataFrame({"id": [], "in_degree": []}, schema={"id": pl.Utf8, "in_degree": pl.UInt32})

    # Start with node core columns
    base_cols = ["id", "name", "node_type", "file_path"]
    existing = [c for c in base_cols if c in nodes.columns]
    if not existing or "id" not in existing:
        # Cannot compute degree without an id column
        return

    degree = nodes.select(existing)

    degree = degree.join(out_deg, on="id", how="left").with_columns(pl.col("out_degree").fill_null(0))
    degree = degree.join(in_deg, on="id", how="left").with_columns(pl.col("in_degree").fill_null(0))
    degree = degree.with_columns((pl.col("in_degree") + pl.col("out_degree")).alias("total_degree"))
    cache.degree_df = degree

    # --- Type distribution counts ---
    if "node_type" in nodes.columns:
        cache.node_type_counts = (
            nodes.group_by("node_type").len().rename({"len": "count"}).sort("count", descending=True)
        )

    if "edge_type" in edges.columns:
        cache.edge_type_counts = (
            edges.group_by("edge_type").len().rename({"len": "count"}).sort("count", descending=True)
        )

    # --- Community detection (cached from NetworkX Louvain) ---
    if data.graph is not None:
        try:
            from networkx.algorithms.community import louvain_communities

            G = data.graph._graph
            undirected = G.to_undirected()
            if len(undirected) > 0:
                communities = louvain_communities(undirected, seed=42)
                records = []
                for comm_id, members in enumerate(communities):
                    for node_id in members:
                        records.append({"id": node_id, "community_id": comm_id})
                if records:
                    cache.community_assignments = pl.DataFrame(records)
        except Exception as exc:
            logger.debug(f"Community detection failed: {exc}")

    # --- DuckDB connection ---
    try:
        con = duckdb.connect()
        con.register("nodes", cache.degree_df if cache.degree_df is not None else nodes)
        con.register("edges", edges)
        if cache.degree_df is not None:
            con.register("degree", cache.degree_df)
        if cache.community_assignments is not None:
            con.register("communities", cache.community_assignments)
        cache.duckdb_con = con
    except Exception as exc:
        logger.debug(f"DuckDB setup failed: {exc}")


def load_dashboard_data(agent_dir: Path) -> DashboardData:
    """Load all analysis artifacts from the .code-context/ directory.

    Tries parquet files first (written by the indexer) for faster loading,
    then falls back to JSON. After all data is loaded, pre-computes
    aggregations into ``DashboardCache`` for efficient downstream queries.

    Args:
        agent_dir: Path to the .code-context/ output directory.

    Returns:
        Populated DashboardData instance.
    """
    data = DashboardData(agent_dir=agent_dir)

    # --- Try parquet first (faster, written by indexer) ---
    parquet_loaded = False
    nodes_parquet = agent_dir / "nodes.parquet"
    edges_parquet = agent_dir / "edges.parquet"

    if nodes_parquet.exists() and edges_parquet.exists():
        try:
            import polars as pl  # ty: ignore[unresolved-import]

            data.nodes_df = pl.read_parquet(nodes_parquet)
            data.edges_df = pl.read_parquet(edges_parquet)
            logger.debug(f"Loaded parquet: {len(data.nodes_df)} nodes, {len(data.edges_df)} edges")

            # Build CodeGraph from parquet data
            data.graph = _build_graph_from_polars(data.nodes_df, data.edges_df)

            # Build graph_raw for views that consume raw dicts, dropping metadata_json if present
            nodes_cols = [c for c in data.nodes_df.columns if c != "metadata_json"]
            edges_cols = [c for c in data.edges_df.columns if c != "metadata_json"]
            data.graph_raw = {
                "nodes": data.nodes_df.select(nodes_cols).to_dicts(),
                "links": data.edges_df.select(edges_cols).to_dicts(),
            }
            parquet_loaded = True
        except Exception as exc:
            logger.warning(f"Parquet loading failed, falling back to JSON: {exc}")
            data.nodes_df = None
            data.edges_df = None

    # --- Fall back to JSON code graph ---
    if not parquet_loaded:
        graph_path = agent_dir / "code_graph.json"
        if graph_path.exists():
            try:
                raw = json.loads(graph_path.read_text(encoding="utf-8"))
                data.graph_raw = raw
                from code_context_agent.tools.graph.model import CodeGraph

                data.graph = CodeGraph.from_node_link_data(raw)
                logger.debug(f"Loaded code graph: {len(raw.get('nodes', []))} nodes")
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                logger.warning(f"Failed to load code graph: {exc}")

    # Load analysis result
    result_path = agent_dir / "analysis_result.json"
    if result_path.exists():
        try:
            data.analysis_result = json.loads(result_path.read_text(encoding="utf-8"))
            logger.debug("Loaded analysis result")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load analysis result: {exc}")

    # Load heuristic summary
    summary_path = agent_dir / "heuristic_summary.json"
    if summary_path.exists():
        try:
            data.heuristic_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            logger.debug("Loaded heuristic summary")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load heuristic summary: {exc}")

    # Load narrative
    narrative_path = agent_dir / "CONTEXT.md"
    if narrative_path.exists():
        data.narrative = narrative_path.read_text(encoding="utf-8")

    # Load signatures
    sig_path = agent_dir / "CONTEXT.signatures.md"
    if sig_path.exists():
        data.signatures = sig_path.read_text(encoding="utf-8")

    # Load bundles
    bundles_dir = agent_dir / "bundles"
    if bundles_dir.is_dir():
        for md_file in sorted(bundles_dir.glob("BUNDLE.*.md")):
            area = md_file.stem.split(".", 1)[1] if "." in md_file.stem else md_file.stem
            data.bundles[area] = md_file.read_text(encoding="utf-8")

    # Fallback: single bundle file
    if not data.bundles:
        bundle_path = agent_dir / "CONTEXT.bundle.md"
        if bundle_path.exists():
            data.bundles["default"] = bundle_path.read_text(encoding="utf-8")

    # Load file manifest
    files_path = agent_dir / "files.all.txt"
    if files_path.exists():
        data.files_list = files_path.read_text(encoding="utf-8")

    # --- If we loaded from JSON but don't have polars DataFrames, create them ---
    if data.nodes_df is None and data.graph_raw:
        try:
            import polars as pl  # ty: ignore[unresolved-import]

            nodes_list = data.graph_raw.get("nodes", [])
            if nodes_list:
                data.nodes_df = pl.DataFrame(nodes_list)
            edges_list = data.graph_raw.get("links", data.graph_raw.get("edges", []))
            if edges_list:
                data.edges_df = pl.DataFrame(edges_list)
        except ImportError:
            pass  # polars not installed

    # Build cache with pre-computed aggregations
    _build_cache(data)

    return data
