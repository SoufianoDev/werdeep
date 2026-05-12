"""Search discovery orchestrator for WeRDeep.

This module provides the SearchDiscovery class that coordinates
search across multiple engines, deduplicates results, computes
relevance scores, and returns immutable DiscoveryReport objects
for agent decision-making.

Key features:
- False success detection: reports "error" if all engines fail,
  "partial" if some fail, "success" only if all succeed.
- Query staggering: delays between engine submissions to reduce
  rate-limit triggers.
- Result caching: LRU cache with TTL to avoid redundant queries.
- Engine health tracking: skips engines in cooldown after failures.

Dependency Inversion: SearchDiscovery accepts BaseSearchEngine
instances, not engine names. The caller decides which engines to use.
"""

import logging
import time
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import urlparse

from werdeep.config.settings import (
    DISCOVERY_CACHE_MAX_SIZE,
    DISCOVERY_CACHE_TTL_SECONDS,
    DISCOVERY_QUERY_STAGGER_MS,
    ENGINE_COOLDOWN_SECONDS,
)
from werdeep.engine.exceptions import CaptchaBlockedError
from werdeep.search.contracts import (
    DiscoveryMetadata,
    DiscoveryReport,
    SearchQuery,
    SearchResultItem,
)
from werdeep.search.engines.base import BaseSearchEngine

logger = logging.getLogger(__name__)


class _QueryCache:
    """LRU cache for discovery query results with TTL expiration.

    Thread-unsafe: caller must synchronize if used across threads.
    """

    def __init__(
        self, max_size: int = DISCOVERY_CACHE_MAX_SIZE, ttl: int = DISCOVERY_CACHE_TTL_SECONDS
    ) -> None:
        self._max_size = max_size
        self._ttl = ttl
        self._store: OrderedDict[str, tuple[list[SearchResultItem], float]] = OrderedDict()

    def get(self, key: str) -> Optional[list[SearchResultItem]]:
        """Return cached results if present and not expired, else None."""
        if key not in self._store:
            return None
        items, timestamp = self._store[key]
        if time.time() - timestamp > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return items

    def put(self, key: str, items: list[SearchResultItem]) -> None:
        """Store results with current timestamp, evicting oldest if at capacity."""
        if key in self._store:
            del self._store[key]
        self._store[key] = (items, time.time())
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._store.clear()


class EngineHealthTracker:
    """Tracks per-engine health status for rate-limit cooldown management.

    Records consecutive failures and timestamps. Engines in cooldown
    are skipped to avoid wasting time on requests that will likely fail.
    """

    def __init__(self, cooldown_seconds: int = ENGINE_COOLDOWN_SECONDS) -> None:
        """Initialize engine health tracker."""
        self._cooldown_seconds = cooldown_seconds
        self._last_failure: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = {}

    def record_success(self, engine_name: str) -> None:
        """Record a successful engine execution."""
        self._consecutive_failures.pop(engine_name, None)
        self._last_failure.pop(engine_name, None)

    def record_failure(self, engine_name: str) -> None:
        """Record a failed engine execution, entering cooldown if needed."""
        self._last_failure[engine_name] = time.time()
        self._consecutive_failures[engine_name] = self._consecutive_failures.get(engine_name, 0) + 1

    def is_available(self, engine_name: str) -> bool:
        """Check if engine is available (not in cooldown)."""
        if engine_name not in self._last_failure:
            return True
        elapsed = time.time() - self._last_failure[engine_name]
        return elapsed >= self._cooldown_seconds

    def get_consecutive_failures(self, engine_name: str) -> int:
        """Return number of consecutive failures for an engine."""
        return self._consecutive_failures.get(engine_name, 0)


class SearchDiscovery:
    """Orchestrates search across multiple engines.

    Dependency Inversion: accepts BaseSearchEngine instances,
    not engine names. The caller decides which engines to use.

    Features:
    - False success detection via status="error"/"partial"
    - Query staggering between engine submissions
    - LRU result caching with TTL
    - Engine health tracking with cooldown
    """

    def __init__(
        self,
        engines: list[BaseSearchEngine],
        max_workers: int = 5,
        stagger_ms: int = DISCOVERY_QUERY_STAGGER_MS,
        query_delay_ms: int = 0,
        cooldown_seconds: int = ENGINE_COOLDOWN_SECONDS,
    ) -> None:
        """Initialize the search discovery orchestrator.

        Args:
            engines: List of BaseSearchEngine instances to query.
            max_workers: Maximum concurrent engine requests.
            stagger_ms: Milliseconds to delay between engine submissions.
            query_delay_ms: Milliseconds to delay between sequential queries.
            cooldown_seconds: Seconds an engine stays in cooldown after failure.

        Raises:
            ValueError: If engines list is empty.
        """
        if not engines:
            raise ValueError("SearchDiscovery requires at least one engine")
        self._engines = tuple(engines)
        self._max_workers = max_workers
        self._stagger_ms = stagger_ms
        self._query_delay_ms = query_delay_ms
        self._cache = _QueryCache()
        self._health = EngineHealthTracker(cooldown_seconds=cooldown_seconds)
        self._last_search_time: float = 0.0

    def search(self, query: SearchQuery) -> DiscoveryReport:
        """Execute search across all engines and return merged results.

        Args:
            query: Immutable SearchQuery with text, domains, and limits.

        Returns:
            Immutable DiscoveryReport with ranked, deduplicated results.
            Status is "error" if all engines failed, "partial" if some
            failed, "success" only if all engines returned results.
        """
        if self._query_delay_ms > 0 and self._last_search_time > 0:
            elapsed_ms = (time.time() - self._last_search_time) * 1000
            remaining = self._query_delay_ms - elapsed_ms
            if remaining > 0:
                time.sleep(remaining / 1000.0)

        start_time = time.time()
        self._last_search_time = start_time

        cache_key = self._cache_key(query)
        cached = self._cache.get(cache_key)
        if cached is not None:
            duration_ms = int((time.time() - start_time) * 1000)
            metadata = DiscoveryMetadata(
                query=query.text,
                domains=query.domains,
                engines_used=(),
                engines_failed=(),
                total_results=len(cached),
                duration_ms=duration_ms,
            )
            return DiscoveryReport(
                status="success",
                query=query.text,
                results=tuple(cached),
                metadata=metadata,
            )

        all_items: list[SearchResultItem] = []
        engines_used: list[str] = []
        engines_failed: list[str] = []
        engines_skipped: list[str] = []
        engine_errors: dict[str, str] = {}

        domains = list(query.domains) if query.domains else None

        available_engines = []
        for engine in self._engines:
            if self._health.is_available(engine.name):
                available_engines.append(engine)
            else:
                engines_skipped.append(engine.name)
                engine_errors[engine.name] = "Engine in cooldown after recent failures"
                logger.info(f"Engine {engine.name} skipped (cooldown)")

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_engine: dict = {}
            for i, engine in enumerate(available_engines):
                if i > 0 and self._stagger_ms > 0:
                    time.sleep(self._stagger_ms / 1000.0)
                future = executor.submit(
                    engine.execute,
                    query.text,
                    domains=domains,
                    max_results=query.max_results,
                )
                future_to_engine[future] = engine

            for future in as_completed(future_to_engine):
                engine = future_to_engine[future]
                try:
                    items = future.result()
                    all_items.extend(items)
                    engines_used.append(engine.name)
                    self._health.record_success(engine.name)
                except CaptchaBlockedError as e:
                    logger.error(f"Engine {engine.name} CAPTCHA blocked: {e.message}")
                    engines_failed.append(engine.name)
                    engine_errors[engine.name] = f"CAPTCHA_BLOCKED: {e.message}"
                    self._health.record_failure(engine.name)
                except Exception as e:
                    logger.error(f"Engine {engine.name} failed: {e}")
                    engines_failed.append(engine.name)
                    engine_errors[engine.name] = str(e)
                    self._health.record_failure(engine.name)

        merged = self._merge_and_rank(all_items, query.max_results)
        duration_ms = int((time.time() - start_time) * 1000)

        metadata = DiscoveryMetadata(
            query=query.text,
            domains=query.domains,
            engines_used=tuple(engines_used),
            engines_failed=tuple(engines_failed + engines_skipped),
            total_results=len(merged),
            duration_ms=duration_ms,
            engine_errors=engine_errors,
        )

        status = self._determine_status(engines_used, engines_failed + engines_skipped, merged)

        if merged:
            self._cache.put(cache_key, merged)

        error_msg = None
        if status == "error":
            failed_names = ", ".join(engines_failed + engines_skipped)
            error_msg = f"All engines failed or unavailable: {failed_names}"
        elif status == "partial":
            failed_names = ", ".join(engines_failed + engines_skipped)
            error_msg = f"Partial results: engines {failed_names} failed or in cooldown"

        return DiscoveryReport(
            status=status,
            query=query.text,
            results=tuple(merged),
            metadata=metadata,
            error=error_msg,
        )

    @staticmethod
    def _determine_status(
        engines_used: list[str],
        engines_failed: list[str],
        merged: list[SearchResultItem],
    ) -> str:
        """Determine report status based on engine outcomes.

        - "success": all engines returned results AND merged is non-empty.
        - "partial": some engines succeeded but some failed, OR all
          engines returned 0 results despite not raising exceptions.
        - "error": no engines succeeded at all.

        False-success fix: engines_used being non-empty with an empty
        merged list means all engines ran but returned zero results,
        which is reported as "partial" rather than "success".
        """
        if not engines_used and not engines_failed:
            return "error"

        if engines_used and not engines_failed:
            if not merged:
                return "partial"
            return "success"

        if engines_used and engines_failed:
            return "partial"

        return "error"

    @staticmethod
    def _cache_key(query: SearchQuery) -> str:
        """Generate cache key from query parameters."""
        domains_str = ",".join(sorted(query.domains))
        return f"{query.text}|{domains_str}|{query.max_results}"

    def _merge_and_rank(
        self, items: list[SearchResultItem], max_results: int
    ) -> list[SearchResultItem]:
        """Merge, deduplicate, detect cross-engine presence, and rank."""
        if not items:
            return []

        url_groups: dict[str, list[SearchResultItem]] = defaultdict(list)
        for item in items:
            normalized = self._normalize_url(item.url)
            url_groups[normalized].append(item)

        merged: list[SearchResultItem] = []
        for url, group in url_groups.items():
            best = self._select_best_item(group)
            engine_names = set(item.source_engine for item in group)
            cross_engine = len(engine_names) >= 2
            score = self._compute_relevance(best, len(engine_names), len(group))

            merged.append(
                SearchResultItem(
                    url=url,
                    title=best.title,
                    snippet=best.snippet,
                    source_engine=best.source_engine,
                    source_domains=best.source_domains,
                    rank=best.rank,
                    relevance_score=score,
                    cross_engine=cross_engine,
                )
            )

        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        return merged[:max_results]

    @staticmethod
    def _select_best_item(group: list[SearchResultItem]) -> SearchResultItem:
        """Select the best item from a group of duplicates.

        Prefers items with the longest snippet, then lowest rank.
        """
        best = group[0]
        for item in group[1:]:
            if len(item.snippet) > len(best.snippet):
                best = item
            elif len(item.snippet) == len(best.snippet) and item.rank < best.rank:
                best = item
        return best

    @staticmethod
    def _compute_relevance(
        item: SearchResultItem, engine_count: int, occurrence_count: int
    ) -> float:
        """Compute relevance score for a discovered item."""
        score = 0.0

        if engine_count >= 3:
            score += 0.35
        elif engine_count >= 2:
            score += 0.25

        if item.rank > 0:
            score += max(0.0, 0.2 * (1.0 - (item.rank - 1) / 20.0))

        if item.snippet:
            snippet_len = len(item.snippet)
            if snippet_len > 200:
                score += 0.15
            elif snippet_len > 100:
                score += 0.10
            elif snippet_len > 0:
                score += 0.05

        score += min(0.15, occurrence_count * 0.05)

        if item.cross_engine:
            score += 0.15

        return min(1.0, score)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for deduplication."""
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        return f"{scheme}://{netloc}{path}"
