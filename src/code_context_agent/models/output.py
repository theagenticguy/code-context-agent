"""Structured output models for agent analysis results.

These models define the shape of the agent's final structured response.
File generation (CONTEXT.md, bundles, etc.) still happens via tools.
The structured output captures the analysis summary and metadata.
"""

from __future__ import annotations

from pydantic import Field

from .base import FrozenModel


class GraphStats(FrozenModel):
    """Code graph statistics from analysis."""

    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    module_count: int = Field(ge=0, default=0)
    hotspot_count: int = Field(ge=0, default=0)


class BusinessLogicItem(FrozenModel):
    """A ranked business logic item discovered during analysis."""

    rank: int = Field(description="Priority rank (1 = highest)")
    name: str = Field(description="Function/class/method name")
    role: str = Field(description="Brief description of business role")
    location: str = Field(description="File path and line reference (e.g., src/auth.py:42)")
    score: float = Field(ge=0.0, le=1.0, description="Relevance score from graph analysis")
    category: str | None = Field(default=None, description="Category: db, auth, validation, workflows, integrations")


class ArchitecturalRisk(FrozenModel):
    """An identified architectural risk."""

    description: str = Field(description="What the risk is")
    severity: str = Field(description="high, medium, or low")
    location: str | None = Field(default=None, description="File or module location")
    mitigation: str | None = Field(default=None, description="Suggested mitigation")


class GeneratedFile(FrozenModel):
    """Record of a file generated during analysis."""

    path: str = Field(description="Relative path to generated file")
    line_count: int = Field(ge=0, description="Number of lines in the file")
    description: str = Field(description="What this file contains")


class AnalysisResult(FrozenModel):
    """Structured output for the complete analysis.

    This model captures the analysis summary returned by the agent.
    The actual files (CONTEXT.md, bundles, etc.) are created by tools.
    """

    status: str = Field(description="completed, partial, or failed")
    summary: str = Field(description="2-3 sentence executive summary")
    total_files_analyzed: int = Field(ge=0, description="Number of files in the repository")
    business_logic_items: list[BusinessLogicItem] = Field(
        default_factory=list,
        description="Ranked business logic items",
    )
    risks: list[ArchitecturalRisk] = Field(
        default_factory=list,
        description="Identified architectural risks",
    )
    generated_files: list[GeneratedFile] = Field(
        default_factory=list,
        description="Files created during analysis",
    )
    graph_stats: GraphStats | None = Field(default=None, description="Code graph statistics")
