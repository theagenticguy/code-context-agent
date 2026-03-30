"""Semantic embedding enrichment for the code graph.

Chunks source code at function/method level using tree-sitter, embeds via
Amazon Titan Text Embeddings V2 on Bedrock (primary), with Cohere Embed 4
fallback. Builds cosine similarity edges and runs Leiden/Louvain community
detection. Content-hash caching avoids re-embedding unchanged chunks.

This module is called by the indexer as an optional enrichment step.
All operations degrade gracefully -- if dependencies are missing or API keys
are not set, the step is skipped with a warning.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from loguru import logger

from .model import CodeEdge, CodeNode, EdgeType, NodeType

if TYPE_CHECKING:
    from .model import CodeGraph

# ---------------------------------------------------------------------------
# Language mapping: file extension -> tree-sitter language name
# ---------------------------------------------------------------------------

_EXT_TO_TS_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

# Tree-sitter node types that represent top-level function/class declarations
# per language. The sets are intentionally broad so we capture all common forms.
_FUNCTION_NODE_TYPES: set[str] = {
    "function_definition",  # Python
    "function_declaration",  # JS/TS/Go
    "function_item",  # Rust
    "method_declaration",  # Java/Go
    "arrow_function",  # JS/TS (top-level const x = () => ...)
}

_CLASS_NODE_TYPES: set[str] = {
    "class_definition",  # Python
    "class_declaration",  # JS/TS/Java
    "struct_item",  # Rust
    "impl_item",  # Rust impl blocks
    "type_declaration",  # Go
}

_METHOD_NODE_TYPES: set[str] = {
    "function_definition",  # Python (inside class body)
    "method_definition",  # JS/TS
    "method_declaration",  # Java
    "function_item",  # Rust (inside impl body)
}

_NODE_TYPE_MAP: dict[str, NodeType] = {
    "function": NodeType.FUNCTION,
    "method": NodeType.METHOD,
    "class": NodeType.CLASS,
}


# ---------------------------------------------------------------------------
# Tree-sitter chunking
# ---------------------------------------------------------------------------


def chunk_code_with_treesitter(
    file_path: str,
    source: str,
    language: str,
) -> list[dict[str, Any]]:
    """Parse source with tree-sitter and extract function/method/class chunks.

    Args:
        file_path: Relative path to the source file.
        source: Source code text.
        language: Tree-sitter language name (e.g. ``"python"``).

    Returns:
        List of chunk dicts with keys: ``id``, ``text``, ``file_path``,
        ``name``, ``type``, ``start_line``, ``end_line``.
    """
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        logger.debug("tree-sitter-language-pack not available -- skipping chunking")
        return []

    try:
        parser = get_parser(language)  # ty: ignore[invalid-argument-type]
    except Exception:  # noqa: BLE001
        logger.debug(f"No tree-sitter grammar for {language}")
        return []

    tree = parser.parse(source.encode())
    chunks: list[dict[str, Any]] = []

    for child in tree.root_node.children:
        _collect_chunks_from_node(child, file_path, source, chunks)

    return chunks


def _collect_chunks_from_node(
    child: Any,
    file_path: str,
    source: str,
    chunks: list[dict[str, Any]],
) -> None:
    """Collect function/method/class chunks from a single top-level tree-sitter node."""
    if child.type in _FUNCTION_NODE_TYPES:
        name = _extract_node_name(child)
        if name:
            chunks.append(_build_chunk(file_path, child, name, "function", source))

    elif child.type in _CLASS_NODE_TYPES:
        _collect_class_chunks(child, file_path, source, chunks)

    elif child.type in ("export_statement", "export_default_declaration"):
        _collect_export_chunks(child, file_path, source, chunks)


def _collect_class_chunks(
    child: Any,
    file_path: str,
    source: str,
    chunks: list[dict[str, Any]],
) -> None:
    """Collect chunks from a class/struct/impl node and its methods."""
    name = _extract_node_name(child)
    if name:
        chunks.append(_build_chunk(file_path, child, name, "class", source))

    body = child.child_by_field_name("body")
    if not body or not name:
        return

    for member in body.children:
        if member.type in _METHOD_NODE_TYPES:
            method_name = _extract_node_name(member)
            if method_name:
                chunks.append(_build_chunk(file_path, member, f"{name}.{method_name}", "method", source))


def _collect_export_chunks(
    child: Any,
    file_path: str,
    source: str,
    chunks: list[dict[str, Any]],
) -> None:
    """Collect chunks from JS/TS export wrapper nodes."""
    for sub in child.children:
        if sub.type in _FUNCTION_NODE_TYPES:
            name = _extract_node_name(sub)
            if name:
                chunks.append(_build_chunk(file_path, sub, name, "function", source))
        elif sub.type in _CLASS_NODE_TYPES:
            name = _extract_node_name(sub)
            if name:
                chunks.append(_build_chunk(file_path, sub, name, "class", source))


def _extract_node_name(node: Any) -> str | None:
    """Extract the name from a tree-sitter node via the ``name`` field."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return name_node.text.decode()
    # Fallback: first identifier/type_identifier child
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "name"):
            return child.text.decode()
    return None


def _build_chunk(
    file_path: str,
    node: Any,
    name: str,
    chunk_type: str,
    source: str,
) -> dict[str, Any]:
    """Build a chunk dict from a tree-sitter node."""
    start_line = node.start_point[0]
    end_line = node.end_point[0]
    text = source.encode()[node.start_byte : node.end_byte].decode(errors="replace")
    node_id = f"{file_path}:{name}:{start_line}"
    return {
        "id": node_id,
        "text": text,
        "file_path": file_path,
        "name": name,
        "type": chunk_type,
        "start_line": start_line,
        "end_line": end_line,
    }


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

_BEDROCK_BATCH_SIZE = 128


def batch_embed_chunks(
    chunks: list[dict[str, Any]],
    model: str = "amazon.titan-embed-text-v2:0",
    region: str = "us-east-1",
) -> np.ndarray:
    """Embed code chunks via Amazon Titan Text Embeddings V2 on Bedrock.

    Falls back to Cohere Embed 4 on Bedrock if Titan fails.

    Args:
        chunks: List of chunk dicts (must have ``"text"`` key).
        model: Bedrock model ID (default: Titan Embed V2).
        region: AWS region for Bedrock.

    Returns:
        Numpy array of shape ``(n_chunks, dim)`` or empty ``(0, 0)`` on failure.
    """
    if not chunks:
        return np.empty((0, 0))

    texts = [c["text"] for c in chunks]

    # Primary: Titan Text Embeddings V2
    embeddings = _embed_bedrock_titan(texts, model, region)
    if embeddings is not None:
        return embeddings

    # Fallback: Bedrock Cohere Embed 4
    embeddings = _embed_bedrock_cohere(texts, region)
    if embeddings is not None:
        return embeddings

    logger.warning("No embedding provider available (configure AWS Bedrock credentials) -- skipping embeddings")
    return np.empty((0, 0))


def _embed_bedrock_titan(texts: list[str], model: str, region: str) -> np.ndarray | None:
    """Embed via Amazon Titan Text Embeddings V2 on Bedrock."""
    try:
        import boto3
    except ImportError:
        logger.debug("boto3 not installed -- cannot use Bedrock")
        return None

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        all_embeddings: list[list[float]] = []

        for text in texts:
            # Titan Embed V2 accepts one text per request
            response = client.invoke_model(
                body=json.dumps(
                    {
                        "inputText": text[:8192],  # Titan V2 max 8K tokens
                        "dimensions": 1024,
                        "normalize": True,
                    },
                ),
                modelId=model,
            )
            body = json.loads(response["body"].read())
            embedding = body.get("embedding")
            if embedding:
                all_embeddings.append(embedding)

        if not all_embeddings:
            return None
        return np.array(all_embeddings, dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Bedrock Titan embedding failed: {exc}")
        return None


def _embed_bedrock_cohere(texts: list[str], region: str) -> np.ndarray | None:
    """Embed via Bedrock Cohere Embed 4 (fallback)."""
    try:
        import boto3
    except ImportError:
        logger.debug("boto3 not installed -- cannot use Bedrock fallback")
        return None

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), _BEDROCK_BATCH_SIZE):
            batch = texts[i : i + _BEDROCK_BATCH_SIZE]
            response = client.invoke_model(
                body=json.dumps({"input_type": "search_document", "texts": batch}),
                modelId="cohere.embed-v4:0",
            )
            body = json.loads(response["body"].read())
            all_embeddings.extend(body.get("embeddings", []))

        if not all_embeddings:
            return None
        return np.array(all_embeddings, dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Bedrock Cohere embedding failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Similarity edges
# ---------------------------------------------------------------------------


def build_similarity_edges(
    node_ids: list[str],
    embeddings: np.ndarray,
    threshold: float = 0.75,
) -> list[tuple[str, str, float]]:
    """Compute cosine similarity and return edges above threshold.

    Args:
        node_ids: IDs corresponding to each row in *embeddings*.
        embeddings: Array of shape ``(n, dim)``.
        threshold: Minimum cosine similarity to create an edge.

    Returns:
        List of ``(source_id, target_id, similarity)`` tuples.
    """
    if embeddings.size == 0 or len(node_ids) < 2:
        return []

    _MAX_SIMILARITY_NODES = 2000
    if len(node_ids) > _MAX_SIMILARITY_NODES:
        logger.warning(
            f"Similarity matrix too large ({len(node_ids)} nodes) -- sampling {_MAX_SIMILARITY_NODES}",
        )
        rng = np.random.default_rng(42)
        indices = rng.choice(len(node_ids), _MAX_SIMILARITY_NODES, replace=False)
        node_ids = [node_ids[i] for i in indices]
        embeddings = embeddings[indices]

    # L2-normalize rows
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normalized = embeddings / norms

    # Cosine similarity matrix
    sim_matrix = normalized @ normalized.T

    # Vectorized upper-triangle extraction (avoids O(n^2) Python loop)
    rows, cols = np.triu_indices(len(node_ids), k=1)
    sims = sim_matrix[rows, cols]
    mask = sims >= threshold
    edges: list[tuple[str, str, float]] = [
        (node_ids[int(r)], node_ids[int(c)], float(s))
        for r, c, s in zip(rows[mask], cols[mask], sims[mask], strict=True)
    ]

    return edges


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------


def cluster_from_edges(
    node_ids: list[str],
    edges: list[tuple[str, str, float]],
) -> list[set[str]]:
    """Detect communities from pre-computed similarity edges via Leiden/Louvain.

    Args:
        node_ids: All node IDs (used as graph vertices).
        edges: Pre-computed ``(source, target, similarity)`` tuples.

    Returns:
        List of communities (sets of node IDs).
    """
    import networkx as nx

    if not edges:
        return []

    g = nx.Graph()
    g.add_nodes_from(node_ids)
    for src, tgt, sim in edges:
        g.add_edge(src, tgt, weight=sim)

    try:
        communities = nx.community.leiden_communities(g, weight="weight", seed=42)
    except (NotImplementedError, nx.NetworkXError, ValueError, RuntimeError):
        try:
            communities = nx.community.louvain_communities(g, weight="weight", seed=42)
        except (nx.NetworkXError, ValueError, RuntimeError):
            return []

    return [set(c) for c in communities]


# ---------------------------------------------------------------------------
# Content-hash caching
# ---------------------------------------------------------------------------


def compute_content_hash(content: str) -> str:
    """Return SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode()).hexdigest()


def load_cached_embedding(cache_dir: Path, content_hash: str) -> np.ndarray | None:
    """Load a cached embedding from disk.

    Args:
        cache_dir: Directory containing ``.npy`` cache files.
        content_hash: SHA-256 hex digest key.

    Returns:
        Numpy array if cached, ``None`` otherwise.
    """
    path = cache_dir / f"{content_hash}.npy"
    if path.exists():
        try:
            return np.load(path)
        except (OSError, ValueError):
            return None
    return None


def save_cached_embedding(cache_dir: Path, content_hash: str, embedding: np.ndarray) -> None:
    """Save an embedding to the cache.

    Args:
        cache_dir: Directory for ``.npy`` cache files.
        content_hash: SHA-256 hex digest key.
        embedding: Array to persist.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(cache_dir / f"{content_hash}.npy", embedding)


# ---------------------------------------------------------------------------
# Confidence + label mapping
# ---------------------------------------------------------------------------


def _similarity_confidence(sim: float) -> float:
    """Map cosine similarity to a confidence score.

    Args:
        sim: Cosine similarity value (expected >= 0.75).

    Returns:
        Confidence between 0.0 and 1.0.
    """
    if sim > 0.90:
        return 0.80
    if sim > 0.80:
        return 0.72
    return 0.65


def _similarity_label(sim: float) -> str:
    """Map cosine similarity to a human-readable label.

    Args:
        sim: Cosine similarity value (expected >= 0.75).

    Returns:
        One of ``"clone_like"``, ``"parallel_impl"``, ``"shared_domain"``.
    """
    if sim > 0.90:
        return "clone_like"
    if sim > 0.80:
        return "parallel_impl"
    return "shared_domain"


# ---------------------------------------------------------------------------
# Main orchestrator (split into sub-steps for readability)
# ---------------------------------------------------------------------------


def _chunk_all_files(
    all_files: list[str],
    repo_path: Path,
) -> list[dict[str, Any]]:
    """Step 1: Read source files and chunk with tree-sitter."""
    all_chunks: list[dict[str, Any]] = []
    for rel_path in all_files:
        ext = Path(rel_path).suffix.lower()
        ts_lang = _EXT_TO_TS_LANG.get(ext)
        if not ts_lang:
            continue

        try:
            source = (repo_path / rel_path).read_text(errors="replace")
        except OSError:
            continue

        all_chunks.extend(chunk_code_with_treesitter(rel_path, source, ts_lang))
    return all_chunks


def _embed_with_cache(
    all_chunks: list[dict[str, Any]],
    cache_dir: Path,
    cache_enabled: bool,
    model: str,
    region: str,
) -> list[np.ndarray]:
    """Step 2: Check cache, embed uncached chunks, save to cache."""
    embeddings_list: list[np.ndarray] = []
    to_embed: list[dict[str, Any]] = []
    to_embed_indices: list[int] = []

    for idx, chunk in enumerate(all_chunks):
        content_hash = compute_content_hash(chunk["text"])
        chunk["_content_hash"] = content_hash

        cached = load_cached_embedding(cache_dir, content_hash) if cache_enabled else None
        if cached is not None:
            embeddings_list.append(cached)
        else:
            embeddings_list.append(np.empty(0))  # placeholder
            to_embed.append(chunk)
            to_embed_indices.append(idx)

    if to_embed:
        logger.info(f"Semantic enrichment: embedding {len(to_embed)} uncached chunks (model={model})")
        new_embeddings = batch_embed_chunks(to_embed, model=model, region=region)

        if new_embeddings.size == 0:
            return embeddings_list  # caller checks for valid embeddings

        for i, embed_idx in enumerate(to_embed_indices):
            embeddings_list[embed_idx] = new_embeddings[i]
            if cache_enabled:
                save_cached_embedding(cache_dir, all_chunks[embed_idx]["_content_hash"], new_embeddings[i])

    return embeddings_list


def _collect_valid_embeddings(
    embeddings_list: list[np.ndarray],
    all_chunks: list[dict[str, Any]],
) -> tuple[list[str], np.ndarray]:
    """Filter valid embeddings and return aligned node IDs + matrix."""
    valid = [e for e in embeddings_list if e.ndim == 1 and e.shape[0] > 0]
    if not valid:
        return [], np.empty((0, 0))

    dim = valid[0].shape[0]
    node_ids: list[str] = []
    vectors: list[np.ndarray] = []

    for idx, emb in enumerate(embeddings_list):
        if emb.ndim == 1 and emb.shape[0] == dim:
            node_ids.append(all_chunks[idx]["id"])
            vectors.append(emb)

    if len(node_ids) < 2:
        return [], np.empty((0, 0))

    return node_ids, np.stack(vectors)


def _ensure_chunk_nodes(
    graph: CodeGraph,
    final_node_ids: list[str],
    all_chunks: list[dict[str, Any]],
) -> None:
    """Ensure all chunk nodes exist in the graph, creating them if needed."""
    chunk_lookup = {c["id"]: c for c in all_chunks}
    for node_id in final_node_ids:
        if graph.has_node(node_id):
            continue
        chunk = chunk_lookup.get(node_id)
        if not chunk:
            continue
        graph.add_node(
            CodeNode(
                id=node_id,
                name=chunk["name"],
                node_type=_NODE_TYPE_MAP.get(chunk["type"], NodeType.FUNCTION),
                file_path=chunk["file_path"],
                line_start=chunk["start_line"],
                line_end=chunk["end_line"],
                metadata={"source": "tree_sitter_chunking"},
            ),
        )


def _add_similarity_edges(
    graph: CodeGraph,
    sim_edges: list[tuple[str, str, float]],
    node_community: dict[str, int],
) -> int:
    """Add SIMILAR_TO edges to the graph from similarity pairs."""
    count = 0
    for src, tgt, sim in sim_edges:
        graph.add_edge(
            CodeEdge(
                source=src,
                target=tgt,
                edge_type=EdgeType.SIMILAR_TO,
                weight=sim,
                confidence=_similarity_confidence(sim),
                metadata={
                    "source": "embedding",
                    "similarity": round(sim, 4),
                    "community_id": node_community.get(src, -1),
                    "label": _similarity_label(sim),
                },
            ),
        )
        count += 1
    return count


def run_semantic_enrichment(
    graph: CodeGraph,
    repo_path: Path,
    output_dir: Path,
    all_files: list[str],
    settings: Any,
) -> int:
    """Run the full semantic embedding enrichment pipeline.

    Steps:
        1. Read source files, chunk with tree-sitter.
        2. Check embedding cache; embed uncached chunks.
        3. Build cosine similarity edges.
        4. Run Leiden/Louvain clustering.
        5. Add ``SIMILAR_TO`` edges to the graph with metadata.

    Args:
        graph: The ``CodeGraph`` to enrich in-place.
        repo_path: Repository root path.
        output_dir: Output directory (cache stored under ``embeddings/``).
        all_files: List of relative file paths in the repo.
        settings: Application settings object (uses ``embedding_*`` attributes).

    Returns:
        Number of ``SIMILAR_TO`` edges added.
    """
    cache_dir = output_dir / "embeddings"
    model = getattr(settings, "embedding_model", "amazon.titan-embed-text-v2:0")
    threshold = getattr(settings, "embedding_similarity_threshold", 0.75)
    cache_enabled = getattr(settings, "embedding_cache_enabled", True)
    region = getattr(settings, "region", "us-east-1")

    # Step 1: Chunk
    all_chunks = _chunk_all_files(all_files, repo_path)
    if not all_chunks:
        logger.info("Semantic enrichment: no function/method chunks found -- skipping")
        return 0
    logger.info(f"Semantic enrichment: {len(all_chunks)} chunks from {len(all_files)} files")

    # Step 2: Embed
    embeddings_list = _embed_with_cache(all_chunks, cache_dir, cache_enabled, model, region)

    # Validate + align
    final_node_ids, embeddings_matrix = _collect_valid_embeddings(embeddings_list, all_chunks)
    if not final_node_ids:
        logger.warning("Semantic enrichment: no valid embeddings produced -- skipping")
        return 0

    # Step 3: Similarity edges
    sim_edges = build_similarity_edges(final_node_ids, embeddings_matrix, threshold)
    logger.info(f"Semantic enrichment: {len(sim_edges)} similarity pairs above threshold {threshold}")

    # Step 4: Cluster (reuse pre-computed edges)
    communities = cluster_from_edges(final_node_ids, sim_edges)
    node_community: dict[str, int] = {}
    for cid, members in enumerate(communities):
        for member in members:
            node_community[member] = cid

    # Step 5: Add to graph
    _ensure_chunk_nodes(graph, final_node_ids, all_chunks)
    edge_count = _add_similarity_edges(graph, sim_edges, node_community)

    logger.info(
        f"Semantic enrichment complete: {edge_count} SIMILAR_TO edges, "
        f"{len(communities)} communities from {len(final_node_ids)} chunks",
    )
    return edge_count
