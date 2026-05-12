"""Search engine implementations for WeRDeep discovery layer.

Each engine implements the BaseSearchEngine interface and provides
search results from a specific search service without requiring
JavaScript execution or API keys.

This module provides the ENGINE_REGISTRY factory for constructing
engine instances by name. The orchestrator never uses the registry
directly - it receives pre-constructed instances via dependency injection.
"""

from werdeep.search.engines.base import BaseSearchEngine
from werdeep.search.engines.ddgs_engine import DdgsEngine

ENGINE_REGISTRY: dict[str, type[BaseSearchEngine]] = {
    "ddgs": DdgsEngine,
}


def create_engine(name: str, timeout: int = 10, backend: str = "auto") -> BaseSearchEngine:
    """Factory: create an engine instance by name.

    Used by the CLI and CrawlerService to construct engines
    from configuration. The orchestrator never calls this -
    it receives pre-constructed instances via DI.

    Args:
        name: Engine identifier (e.g., "ddgs").
        timeout: Per-engine request timeout in seconds.
        backend: ddgs backend selection (e.g., "auto", "bing,brave,google").

    Returns:
        Constructed BaseSearchEngine instance.

    Raises:
        ValueError: If the engine name is not in the registry.
    """
    cls = ENGINE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown engine: {name}. Available: {', '.join(ENGINE_REGISTRY)}")
    if name == "ddgs":
        return cls(timeout=timeout, backend=backend)
    return cls(timeout=timeout)


__all__ = [
    "BaseSearchEngine",
    "DdgsEngine",
    "ENGINE_REGISTRY",
    "create_engine",
]
