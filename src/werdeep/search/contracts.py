"""Data contracts for the WeRDeep search discovery layer.

All models are frozen (immutable) value objects. They represent
the strict data contracts between the LLM Agent and WeRDeep.
No model may exist in an invalid or incomplete state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass(frozen=True)
class SearchQuery:
    """Immutable input contract for a discovery operation.

    The LLM Agent constructs this object (or provides it via JSON).
    WeRDeep never mutates it.

    Attributes:
        text: The search query string.
        domains: Tuple of domains for site: filtering.
                 Empty tuple = raw search (no site: prefix).
        max_results: Maximum number of results to return.
        timeout: Per-engine request timeout in seconds.
    """

    text: str
    domains: tuple[str, ...] = ()
    max_results: int = 20
    timeout: int = 10

    def __post_init__(self) -> None:
        """Validate contract invariants at construction time."""
        if not self.text or not self.text.strip():
            raise ValueError("SearchQuery.text must not be empty")
        if self.max_results < 1:
            raise ValueError("SearchQuery.max_results must be >= 1")
        if self.timeout < 1:
            raise ValueError("SearchQuery.timeout must be >= 1")

    @classmethod
    def from_json(cls, path: str | Path) -> SearchQuery:
        """Construct a SearchQuery from an agent-provided JSON file.

        The agent is responsible for writing the file and cleaning
        it up after WeRDeep reads it. WeRDeep never creates or deletes
        this file.

        Expected JSON schema:
            {
                "query": "string (required)",
                "domains": ["list", "of", "strings"],
                "engines": ["duckduckgo", "bing"],
                "max_results": 20
            }

        The "engines" field is NOT stored on SearchQuery. It is
        consumed by the CLI to construct engine instances.

        Args:
            path: Path to the JSON file.

        Returns:
            Constructed SearchQuery.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If required fields are missing or invalid.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        query_text = data.get("query")
        if not query_text:
            raise ValueError("JSON config must contain a non-empty 'query' field")

        return cls(
            text=query_text,
            domains=tuple(data.get("domains", [])),
            max_results=data.get("max_results", 20),
            timeout=data.get("timeout", 10),
        )


@dataclass(frozen=True)
class SearchResultItem:
    """Immutable output contract for a single discovered URL.

    This object is NEVER constructed in an invalid state.
    It is only produced by BaseSearchEngine._enrich_results(),
    which is the single authorized construction site.

    Attributes:
        url: The discovered URL (normalized).
        title: Page title from search engine.
        snippet: Short description from search engine.
        source_engine: Engine that returned this result.
        source_domains: Domains that were targeted (empty = raw search).
        rank: 1-based position in engine results.
        relevance_score: Computed relevance score 0.0-1.0.
        cross_engine: True if this URL appeared in 2+ engines.
    """

    url: str
    title: str
    snippet: str
    source_engine: str
    source_domains: tuple[str, ...]
    rank: int
    relevance_score: float
    cross_engine: bool

    def __post_init__(self) -> None:
        """Clamp numeric fields to valid ranges."""
        if self.rank < 0:
            object.__setattr__(self, "rank", 0)
        if not 0.0 <= self.relevance_score <= 1.0:
            object.__setattr__(
                self,
                "relevance_score",
                max(0.0, min(1.0, self.relevance_score)),
            )


@dataclass(frozen=True)
class DiscoveryMetadata:
    """Immutable session-level metadata for a discovery operation.

    Attributes:
        query: Original search query string.
        domains: Domains that were targeted.
        engines_used: Engines that returned results successfully.
        engines_failed: Engines that failed.
        total_results: Total number of results after merge.
        duration_ms: Total processing time in milliseconds.
        engine_errors: Mapping of engine name to error description.
    """

    query: str
    domains: tuple[str, ...]
    engines_used: tuple[str, ...]
    engines_failed: tuple[str, ...]
    total_results: int
    duration_ms: int
    engine_errors: dict[str, str] = None

    def __post_init__(self) -> None:
        """Initialize default engine_errors to empty dict if not provided."""
        if self.engine_errors is None:
            object.__setattr__(self, "engine_errors", {})


@dataclass(frozen=True)
class DiscoveryReport:
    """Immutable output contract for a complete discovery operation.

    This is the top-level object returned to the LLM Agent.

    Attributes:
        status: Execution status ("success" or "error").
        query: Original search query string.
        results: Tuple of discovered items.
        metadata: Session metadata.
        error: Error message if status is "error".
    """

    status: Literal["success", "error", "partial"]
    query: str
    results: tuple[SearchResultItem, ...]
    metadata: DiscoveryMetadata
    error: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate status value."""
        valid = ("success", "error", "partial")
        if self.status not in valid:
            raise ValueError(f"Invalid status: {self.status}. Must be one of {valid}")
