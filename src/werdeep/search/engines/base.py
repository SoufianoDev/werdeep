"""Abstract base class and internal types for search engine implementations.

This module defines:
- _RawParsedHit: Internal NamedTuple for raw HTML extraction results.
  Never crosses module boundaries.
- RequestConfig: Immutable HTTP request configuration (internal to engines).
- BaseSearchEngine: The professional contract for any search engine.
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

import requests
from bs4 import BeautifulSoup

from werdeep.config.ssl_bootstrap import get_ca_bundle
from werdeep.search.contracts import SearchResultItem

logger = logging.getLogger(__name__)


class _RawParsedHit(NamedTuple):
    """Internal DTO for raw HTML extraction results.

    This type NEVER crosses module boundaries. It exists solely
    as the return type of _parse_html() and the input type of
    _enrich_results(). It contains only raw extracted data -
    no business logic fields like source_engine or rank.
    """

    url: str
    title: str
    snippet: str


@dataclass(frozen=True)
class RequestConfig:
    """Immutable HTTP request configuration (internal to engines).

    Attributes:
        url: Full URL to request.
        method: HTTP method (GET or POST).
        headers: HTTP headers to include.
        params: Query parameters.
        data: POST body data.
    """

    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    data: dict[str, str] = field(default_factory=dict)


_UA_POOL: list[str] = [
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0"),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"),
]

_RETRY_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}
_DEFAULT_MAX_RETRIES: int = 3
_DEFAULT_RETRY_DELAY: float = 1.0


class BaseSearchEngine(ABC):
    """Professional contract for any search engine.

    Open/Closed Principle: New engines extend this class without
    modifying the orchestrator or any other engine.

    Dependency Inversion: The orchestrator depends on this
    abstraction, not on concrete engine implementations.

    Subclasses MUST implement:
        - name (property)
        - execute() or both _build_request() and _parse_html()

    Subclasses MUST NOT override:
        - _fetch() - shared HTTP transport with retry
        - _enrich_results() - shared result construction
    """

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY,
    ) -> None:
        """Initialize search engine with request timeout and retry config."""
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._session: Optional[requests.Session] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique engine identifier (e.g., "ddgs")."""

    def execute(
        self,
        query: str,
        *,
        domains: Optional[list[str]] = None,
        max_results: int = 10,
        page: int = 1,
    ) -> list[SearchResultItem]:
        """Execute a search and return structured results.

        This is the ONLY public method. Template Method pattern:
        the algorithm skeleton is fixed; subclasses provide
        _build_request() and _parse_html().
        """
        config = self._build_request(query, domains, page)
        html = self._fetch(config)
        if not html:
            return []
        raw_hits = self._parse_html(html)
        return self._enrich_results(raw_hits, domains, max_results)

    @abstractmethod
    def _build_request(self, query: str, domains: Optional[list[str]], page: int) -> RequestConfig:
        """Build an HTTP request configuration for this engine.

        Args:
            query: Raw search query string.
            domains: Optional domain list for site: filtering.
                     None or empty = raw search.
            page: Result page number (1-based).
        """

    def _parse_html(self, html: str) -> list[_RawParsedHit]:
        """Parse raw HTML into raw extraction hits.

        Template Method: tries _extract_primary first, falls
        back to _extract_fallback if no results found.
        """
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        hits = self._extract_primary(soup)
        if not hits:
            hits = self._extract_fallback(soup)
        return hits

    @abstractmethod
    def _extract_primary(self, soup: BeautifulSoup) -> list[_RawParsedHit]:
        """Extract results using engine-specific primary selectors."""

    @abstractmethod
    def _extract_fallback(self, soup: BeautifulSoup) -> list[_RawParsedHit]:
        """Extract results using engine-specific fallback selectors."""

    def _fetch(self, config: RequestConfig) -> str:
        """Execute HTTP request with retry and exponential backoff.

        Retries on 429 and 5xx status codes up to _max_retries times
        with exponential backoff (_retry_delay * 2^attempt).

        Not overridable.
        """
        for attempt in range(self._max_retries + 1):
            try:
                headers = {**config.headers}
                if "User-Agent" not in headers:
                    headers["User-Agent"] = random.choice(_UA_POOL)

                response = self._get_session().request(
                    method=config.method,
                    url=config.url,
                    headers=headers,
                    params=config.params,
                    data=config.data,
                    timeout=self._timeout,
                    allow_redirects=True,
                )

                if response.status_code in _RETRY_STATUS_CODES:
                    if attempt < self._max_retries:
                        delay = self._retry_delay * (2**attempt)
                        logger.warning(
                            f"Engine {self.name}: HTTP {response.status_code}, "
                            f"retry {attempt + 1}/{self._max_retries} after {delay:.1f}s"
                        )
                        time.sleep(delay)
                        continue
                    logger.warning(
                        f"Engine {self.name}: HTTP {response.status_code} "
                        f"after {self._max_retries} retries"
                    )
                    return ""

                response.raise_for_status()
                return response.text

            except requests.exceptions.Timeout:
                if attempt < self._max_retries:
                    delay = self._retry_delay * (2**attempt)
                    logger.warning(
                        f"Engine {self.name}: timeout, "
                        f"retry {attempt + 1}/{self._max_retries} after {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue
                logger.warning(f"Engine {self.name}: timeout after {self._max_retries} retries")
                return ""

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in _RETRY_STATUS_CODES and attempt < self._max_retries:
                    delay = self._retry_delay * (2**attempt)
                    logger.warning(
                        f"Engine {self.name}: HTTP {status}, "
                        f"retry {attempt + 1}/{self._max_retries} after {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue
                logger.warning(f"Engine {self.name}: HTTP {status}")
                return ""

            except requests.exceptions.RequestException as e:
                if attempt < self._max_retries:
                    delay = self._retry_delay * (2**attempt)
                    logger.warning(
                        f"Engine {self.name}: request failed, "
                        f"retry {attempt + 1}/{self._max_retries} after {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                logger.warning(f"Engine {self.name}: request failed after retries: {e}")
                return ""

        return ""

    def _enrich_results(
        self,
        raw_hits: list[_RawParsedHit],
        domains: Optional[list[str]],
        max_results: int,
    ) -> list[SearchResultItem]:
        """Construct SearchResultItem from raw parsed hits.

        This is the ONLY authorized construction site for
        SearchResultItem. No other code may construct it.
        """
        domain_tuple = tuple(domains) if domains else ()
        enriched: list[SearchResultItem] = []
        for i, hit in enumerate(raw_hits[:max_results]):
            enriched.append(
                SearchResultItem(
                    url=hit.url,
                    title=hit.title,
                    snippet=hit.snippet,
                    source_engine=self.name,
                    source_domains=domain_tuple,
                    rank=i + 1,
                    relevance_score=0.0,
                    cross_engine=False,
                )
            )
        return enriched

    @staticmethod
    def _construct_domain_query(query: str, domains: list[str]) -> str:
        """Construct a site:-prefixed query from domains.

        Pure function: ("python async", ["github.com", "gitlab.com"])
        -> "site:github.com OR site:gitlab.com python async"

        Returns raw query unchanged if domains is empty.
        """
        if not domains:
            return query
        site_clauses = " OR ".join(f"site:{d}" for d in domains)
        return f"{site_clauses} {query}"

    def _effective_query(self, query: str, domains: Optional[list[str]]) -> str:
        """Return query with site: prefixes if domains provided."""
        return self._construct_domain_query(query, domains) if domains else query

    @staticmethod
    def _validate_url(url: str) -> str:
        """Return url if it is an absolute HTTP(S) URL, else empty string."""
        if not url:
            return ""
        return url if url.startswith(("http://", "https://")) else ""

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Remove extra whitespace from extracted text."""
        if not text:
            return ""
        return " ".join(text.split()).strip()

    def _get_session(self) -> requests.Session:
        """Lazy-initialized requests session with UA rotation."""
        if self._session is None:
            self._session = requests.Session()
            ca_bundle = get_ca_bundle()
            if ca_bundle:
                self._session.verify = ca_bundle
            self._session.headers.update(self._rotated_headers())
        return self._session

    @staticmethod
    def _rotated_headers() -> dict[str, str]:
        """HTTP headers with a randomly selected User-Agent."""
        return {
            "User-Agent": random.choice(_UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
