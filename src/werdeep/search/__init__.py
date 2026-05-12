"""Search discovery module for WeRDeep.

This module provides the discovery layer that converts keyword queries
into structured search results from multiple engines. It is designed as
a stateless tool for LLM agent orchestration.

Public API:
    - SearchDiscovery: Orchestrator that queries multiple engines
    - SearchQuery: Immutable input contract
    - SearchResultItem: Immutable output contract per URL
    - DiscoveryReport: Immutable top-level output contract
    - DiscoveryMetadata: Immutable session metadata
"""

from werdeep.search.contracts import (
    DiscoveryMetadata,
    DiscoveryReport,
    SearchQuery,
    SearchResultItem,
)
from werdeep.search.discovery import EngineHealthTracker, SearchDiscovery

__all__ = [
    "SearchDiscovery",
    "SearchQuery",
    "SearchResultItem",
    "DiscoveryReport",
    "DiscoveryMetadata",
    "EngineHealthTracker",
]
