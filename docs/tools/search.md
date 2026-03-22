# BM25 Search

The BM25 search tool provides ranked full-text search across the codebase using the [BM25 (Okapi)](https://en.wikipedia.org/wiki/Okapi_BM25) algorithm. Unlike ripgrep (exact pattern matching), BM25 ranks results by relevance -- terms appearing in fewer files score higher.

## When to Use BM25 vs ripgrep

| Use Case | Tool |
|----------|------|
| Exact string or regex match | `rg_search` |
| Concept-level search ("authentication flow") | `bm25_search` |
| Too many ripgrep results to be useful | `bm25_search` |
| Finding related code without exact terms | `bm25_search` |
| Counting occurrences per file | `rg_search` |

## Tool

### `bm25_search`

Ranked text search using the BM25 algorithm. Builds an in-memory index from all files in the repository (or from `files.all.txt` if available from a prior analysis), tokenizes content with camelCase/snake_case splitting, and returns results ranked by TF-IDF-like relevance scoring.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | required | Search query (natural language or code terms) |
| `repo_path` | `str` | required | Absolute path to the repository |
| `top_k` | `int` | `20` | Maximum results to return |
| `rebuild` | `bool` | `false` | Force rebuild the index (default: reuse cached) |

Returns ranked results with file path, BM25 score, and matching lines with matched tokens highlighted.

## How It Works

1. **Index construction** -- Reads all files from `files.all.txt` (or falls back to `rglob` capped at 5000 files). Each file is tokenized: camelCase split, snake_case split, lowercased, short tokens filtered.
2. **BM25 scoring** -- Uses `rank_bm25.BM25Okapi` for scoring. Terms that appear in fewer documents receive higher weight (inverse document frequency).
3. **Result assembly** -- Results are ranked by score. For each hit, up to 3 matching lines are returned with the specific tokens that matched.
4. **Caching** -- The index is cached per repository path. Subsequent searches reuse the cached index unless `rebuild=true`.

## Example

```python
# Find code related to authentication
bm25_search("authentication login user session", "/path/to/repo")

# Returns:
{
    "status": "success",
    "query": "authentication login user session",
    "total_documents": 342,
    "results": [
        {
            "path": "src/auth/service.py",
            "score": 12.45,
            "matching_lines": [
                {"line": 15, "text": "class AuthenticationService:", "matched_tokens": ["authentication"]}
            ]
        }
    ],
    "count": 8
}
```

## Tokenization

The tokenizer splits on non-alphanumeric characters, camelCase boundaries, and underscores. Tokens shorter than 2 characters are filtered. This means `getUserAuth` becomes `["get", "user", "auth"]` and `get_user_auth` also becomes `["get", "user", "auth"]`.
