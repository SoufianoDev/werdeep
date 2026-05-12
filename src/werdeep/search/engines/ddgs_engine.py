"""ddgs-based search engine with multi-backend aggregation.

Uses the ddgs library (MIT-licensed) which provides HTML scraping
across 9+ search backends (Google, Bing, Brave, DuckDuckGo, Yahoo,
Mojeek, Yandex, etc.) without requiring API keys or JavaScript.

This engine replaces the previous per-engine scrapers (DuckDuckGo,
Brave, Bing) with a single unified interface that automatically
distributes queries across backends.
"""

import logging
import time
from typing import Optional

import requests as _http_requests
from ddgs import DDGS
from ddgs.exceptions import RatelimitException, TimeoutException

from werdeep.engine.exceptions import CaptchaBlockedError
from werdeep.search.contracts import SearchResultItem
from werdeep.search.engines.base import BaseSearchEngine, _RawParsedHit

logger = logging.getLogger(__name__)

_BACKENDS = frozenset(
    {
        "auto",
        "bing",
        "brave",
        "duckduckgo",
        "google",
        "yahoo",
        "mojeek",
        "yandex",
        "wikipedia",
    }
)

_DDGS_MAX_RETRIES: int = 3
_DDGS_RETRY_DELAY: float = 2.0

_CAPTCHA_INDICATORS = (
    "anomaly.js",
    "Select all squares",
    "verify you are human",
    "captcha",
    "cf-challenge",
)


class DdgsEngine(BaseSearchEngine):
    """Multi-backend search engine powered by ddgs.

    Supports 9+ search backends with automatic rotation and
    rate-limit awareness. Uses ddgs's built-in scraping that
    handles HTML parsing internally.

    Attributes:
        _backend: Comma-separated backend names or "auto".
    """

    _BACKEND: str = "auto"

    @property
    def name(self) -> str:
        """Return the unique engine identifier."""
        return "ddgs"

    def __init__(self, timeout: int = 10, backend: str = "auto") -> None:
        """Initialize DdgsEngine with backend selection."""
        super().__init__(timeout=timeout)
        backends = [b.strip() for b in backend.split(",") if b.strip()]
        valid = [b for b in backends if b in _BACKENDS]
        if not valid:
            valid = ["auto"]
        self._backend = ",".join(valid) if len(valid) > 1 else valid[0]

    def execute(
        self,
        query: str,
        *,
        domains: Optional[list[str]] = None,
        max_results: int = 10,
        page: int = 1,
    ) -> list[SearchResultItem]:
        """Execute search using ddgs library.

        Overrides BaseSearchEngine.execute() because ddgs handles
        its own HTTP transport and HTML parsing internally.

        Retries on RatelimitException with exponential backoff
        before re-raising.

        Args:
            query: Raw search query string.
            domains: Optional domain list for site: filtering.
            max_results: Maximum results to return.
            page: Result page number (1-based).

        Returns:
            List of SearchResultItem objects.

        Raises:
            RatelimitException: If rate-limited after all retries.
            TimeoutException: If request times out.
            CaptchaBlockedError: If a CAPTCHA challenge is detected.
        """
        effective_query = self._effective_query(query, domains)
        raw_hits: list[_RawParsedHit] = []

        last_exception: Optional[Exception] = None
        for attempt in range(_DDGS_MAX_RETRIES + 1):
            try:
                with DDGS() as ddgs:
                    results = ddgs.text(
                        effective_query,
                        max_results=max_results * 2 if page > 1 else max_results,
                        backend=self._backend,
                    )

                if results:
                    offset = (page - 1) * max_results
                    page_results = results[offset : offset + max_results]
                    for r in page_results:
                        url = self._validate_url(r.get("href", ""))
                        if not url:
                            continue
                        title = self._sanitize_text(r.get("title", ""))
                        snippet = self._sanitize_text(r.get("body", ""))
                        raw_hits.append(_RawParsedHit(url=url, title=title, snippet=snippet))
                else:
                    captcha_error = self._detect_captcha(effective_query)
                    if captcha_error:
                        raise captcha_error

                last_exception = None
                break

            except RatelimitException:
                last_exception = RatelimitException()
                if attempt < _DDGS_MAX_RETRIES:
                    delay = _DDGS_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"Engine {self.name}: rate-limited by backend, "
                        f"retry {attempt + 1}/{_DDGS_MAX_RETRIES} after {delay:.1f}s"
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        f"Engine {self.name}: rate-limited after {_DDGS_MAX_RETRIES} retries"
                    )
                    raise
            except TimeoutException:
                logger.warning(f"Engine {self.name}: request timed out")
                raise
            except CaptchaBlockedError:
                raise
            except Exception as e:
                logger.error(f"Engine {self.name}: unexpected error: {e}")
                return []

        if last_exception is not None:
            raise last_exception

        return self._enrich_results(raw_hits, domains, max_results)

    @staticmethod
    def _detect_captcha(query: str) -> Optional[CaptchaBlockedError]:
        """Check for CAPTCHA indicators by making a lightweight request.

        When ddgs.text() returns empty results, this method checks
        whether the search engine is serving a CAPTCHA challenge
        rather than genuinely having no results.

        Args:
            query: The search query that returned empty results.

        Returns:
            CaptchaBlockedError if CAPTCHA detected, None otherwise.
        """
        try:
            from werdeep.config.ssl_bootstrap import get_ca_bundle

            check_url = "https://html.duckduckgo.com/html/?q=" + query.replace(" ", "+")
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            ca_bundle = get_ca_bundle()
            resp = _http_requests.get(
                check_url,
                headers=headers,
                timeout=5,
                allow_redirects=True,
                verify=ca_bundle if ca_bundle else True,
            )
            body_lower = resp.text.lower()
            for indicator in _CAPTCHA_INDICATORS:
                if indicator.lower() in body_lower:
                    logger.warning(f"Engine ddgs: CAPTCHA detected (indicator: '{indicator}')")
                    return CaptchaBlockedError(
                        f"CAPTCHA challenge detected for query '{query}' (indicator: '{indicator}')"
                    )
        except Exception as e:
            logger.debug(f"Engine ddgs: CAPTCHA detection check failed: {e}")

        return None

    def _build_request(self, query: str, domains: list[str] | None, page: int):
        """Not used by DdgsEngine — ddgs handles its own transport."""
        raise NotImplementedError("DdgsEngine uses ddgs library directly")

    def _extract_primary(self, soup):
        """Not used by DdgsEngine — ddgs handles its own parsing."""
        raise NotImplementedError("DdgsEngine uses ddgs library directly")

    def _extract_fallback(self, soup):
        """Not used by DdgsEngine — ddgs handles its own parsing."""
        raise NotImplementedError("DdgsEngine uses ddgs library directly")
