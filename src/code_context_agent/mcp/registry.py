"""Multi-repo registry tracking all analyzed repositories.

Maintains a central registry at ~/.code-context/registry.json so that
MCP clients can discover and switch between analyzed codebases.
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_context_agent.config import DEFAULT_OUTPUT_DIR
from code_context_agent.models.base import FrozenModel
from code_context_agent.tools.graph.model import CodeGraph

REGISTRY_DIR = Path.home() / ".code-context"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
GRAPH_CACHE_TTL = 300  # 5 minutes


class RepoEntry(FrozenModel):
    """A registered repository entry."""

    path: str
    alias: str
    analyzed_at: str  # ISO 8601 timestamp
    graph_exists: bool = False
    artifact_count: int = 0


class Registry:
    """Manages a central registry of analyzed repositories."""

    def __init__(self, registry_path: Path = REGISTRY_FILE) -> None:  # noqa: D107
        self._path = registry_path
        self._graph_cache: dict[str, tuple[float, CodeGraph]] = {}  # alias -> (timestamp, graph)

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"repos": {}}
        return json.loads(self._path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp file then rename
        with tempfile.NamedTemporaryFile(mode="w", dir=self._path.parent, suffix=".tmp", delete=False) as f:
            json.dump(data, f, indent=2)
            tmp_path = Path(f.name)
        tmp_path.rename(self._path)

    def register(self, alias: str, repo_path: str) -> RepoEntry:
        """Register a repo. Auto-detects graph existence and artifact count."""
        data = self._read()
        output_dir = Path(repo_path) / DEFAULT_OUTPUT_DIR
        graph_exists = (output_dir / "code_graph.json").exists()
        artifacts = len(list(output_dir.iterdir())) if output_dir.exists() else 0

        entry = RepoEntry(
            path=str(Path(repo_path).resolve()),
            alias=alias,
            analyzed_at=datetime.now(UTC).isoformat(),
            graph_exists=graph_exists,
            artifact_count=artifacts,
        )
        data["repos"][alias] = entry.model_dump()
        self._write(data)
        return entry

    def unregister(self, alias: str) -> bool:
        """Remove a repo from the registry. Returns True if it existed."""
        data = self._read()
        if alias in data["repos"]:
            del data["repos"][alias]
            self._write(data)
            self._graph_cache.pop(alias, None)
            return True
        return False

    def list_repos(self) -> list[dict[str, Any]]:
        """List all registered repos."""
        data = self._read()
        return list(data["repos"].values())

    def get_repo(self, alias: str) -> dict[str, Any] | None:
        """Get a single repo entry by alias."""
        data = self._read()
        return data["repos"].get(alias)

    def find_by_path(self, repo_path: str) -> str | None:
        """Find alias by repo path (exact match on resolved path)."""
        resolved = str(Path(repo_path).resolve())
        data = self._read()
        for alias, entry in data["repos"].items():
            if entry["path"] == resolved:
                return alias
        return None

    def load_graph(self, alias: str) -> CodeGraph | None:
        """Load graph with caching (5-min TTL)."""
        now = time.time()
        if alias in self._graph_cache:
            ts, graph = self._graph_cache[alias]
            if now - ts < GRAPH_CACHE_TTL:
                return graph

        entry = self.get_repo(alias)
        if not entry:
            return None

        graph_path = Path(entry["path"]) / DEFAULT_OUTPUT_DIR / "code_graph.json"
        if not graph_path.exists():
            return None

        graph_data = json.loads(graph_path.read_text())
        graph = CodeGraph.from_node_link_data(graph_data)
        self._graph_cache[alias] = (now, graph)
        return graph
