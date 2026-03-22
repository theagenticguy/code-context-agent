# ADR-0008: BM25 Ranked Text Search

**Date**: 2026-03-22

**Status**: accepted

## Context

ripgrep (`rg_search` tool) provides exact pattern matching but returns results in file-system order with no relevance ranking. When an AI agent searches for a concept like "authentication flow" or "error handling strategy," it needs results ranked by relevance rather than a flat list of line-matching hits.

The agent frequently performs concept-oriented searches where the goal is to find the most relevant files and code regions, not just exact string matches. Without ranking, the agent must read through all matches and determine relevance itself, consuming context window and tool calls.

Alternatives considered:

- **Embedding-based semantic search**: High quality results but requires a vector database, embedding model, and pre-indexing pipeline. Heavy infrastructure for a CLI tool.
- **TF-IDF**: Simpler than embeddings but BM25 is strictly better for information retrieval (accounts for document length normalization and term frequency saturation).
- **ripgrep with post-processing**: Could count matches per file, but wouldn't provide true relevance scoring within and across files.

## Decision

Add BM25 search using the `rank_bm25` library (BM25Okapi algorithm) as a new tool alongside ripgrep.

Key design choices:

- **Pure Python implementation** via `rank_bm25` — no compilation step, no external service, no native dependencies
- **camelCase/snake_case-aware tokenizer** that splits `getUserName` into `[get, user, name]` and `get_user_name` into `[get, user, name]`, improving match quality for code identifiers
- **Module-level index caching** so the BM25 index is built once per analysis session and reused across searches
- **Complementary to ripgrep**, not a replacement — ripgrep remains the tool for exact pattern matching, BM25 handles concept/relevance searches

## Consequences

**Positive:**

- AI agent gets ranked results for concept searches, reducing wasted tool calls on irrelevant matches
- Pure Python means no build complexity, works on all platforms without compilation
- Module-level caching amortizes the indexing cost across multiple searches in a session
- Code-aware tokenization produces better rankings for identifier-heavy searches than generic text tokenization

**Negative:**

- Initial index build requires reading file contents into memory; large repos will have higher memory usage during indexing
- BM25 is a lexical algorithm — it cannot find semantically similar code that uses different terminology (e.g., searching "auth" won't rank "login" highly)
- Adds `rank_bm25` as a runtime dependency

**Neutral:**

- No semantic/embedding search yet; this is a future enhancement that could layer on top of BM25 for hybrid retrieval
- The tokenizer is tuned for code; prose-heavy files (README, docs) may not rank as well
