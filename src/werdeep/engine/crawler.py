"""Core Scrapy-based crawler module.

This module provides the web crawling functionality using Scrapy
for deep web content retrieval.
"""

import fnmatch
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import scrapy
from scrapy.http import Response, TextResponse
from scrapy.linkextractors import LinkExtractor
from werdeep.engine.parser import ContentParser

from werdeep.config.settings import (
    DUPLICATE_WARNING_THRESHOLD,
    LOW_RELEVANCE_PATHS,
    MAX_CONTENT_SIZE_BYTES,
    PROGRESS_INTERVAL_PAGES,
    PROGRESS_INTERVAL_SECONDS,
    RETRY_STATUS_CODES,
)
from werdeep.engine.content_analyzer import ContentAnalyzer
from werdeep.engine.models import ResultItem

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication comparison.

    Args:
        url: URL to normalize.

    Returns:
        Normalized URL string.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    query = urlencode(sorted(parse_qsl(parsed.query)))
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


class WeRDeepSpider(scrapy.Spider):
    """Scrapy Spider for deep web crawling.

    Attributes:
        name: Spider name.
        query: Search query or seed URL.
        max_depth: Maximum crawl depth.
        max_pages: Maximum pages to crawl.
        timeout: Request timeout in seconds.
        relevance_threshold: Relevance filtering threshold.
        robots_whitelist: List of whitelisted path patterns.
        max_retries: Maximum retry attempts.
        retry_delay: Base retry delay.
        quiet: Suppress progress output.
        no_dedup: Disable deduplication.
    """

    name = "werdeep"

    def __init__(
        self,
        query: str = "",
        seed_urls: Optional[List[str]] = None,
        max_depth: int = 3,
        max_pages: int = 100,
        timeout: int = 300,
        relevance_threshold: float = 0.3,
        robots_whitelist: str = "",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        quiet: bool = False,
        no_dedup: bool = False,
        deterministic: bool = False,
        **kwargs,
    ):
        """Initialize WeRDeep spider.

        Args:
            query: Search query (used for content analysis context).
            seed_urls: List of seed URLs to crawl. Takes priority over query
                if both are provided.
            max_depth: Maximum crawl depth (1-5).
            max_pages: Maximum pages to crawl.
            timeout: Request timeout in seconds.
            relevance_threshold: Relevance filtering threshold (0.0-1.0).
            robots_whitelist: Comma-separated whitelist patterns.
            max_retries: Maximum retry attempts.
            retry_delay: Base retry delay for backoff.
            quiet: Suppress progress output.
            no_dedup: Disable deduplication.
            deterministic: Sort extracted links by URL before yielding
                requests for reproducible crawl results.
            **kwargs: Additional arguments passed to parent class.
        """
        super().__init__(**kwargs)
        self.query: str = query
        self.seed_urls: List[str] = seed_urls or []
        self.max_depth: int = max_depth
        self.max_pages: int = max_pages
        self.timeout: int = timeout
        self.relevance_threshold: float = relevance_threshold
        self.robots_whitelist: List[str] = [
            p.strip() for p in robots_whitelist.split(",") if p.strip()
        ]
        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay
        self.quiet: bool = quiet
        self.no_dedup: bool = no_dedup
        self.deterministic: bool = deterministic
        self.parser: ContentParser = ContentParser()
        self.content_analyzer: ContentAnalyzer = ContentAnalyzer(query=query)
        self.visited_urls: Set[str] = set()
        self.results: list[ResultItem] = []
        self.request_depth: Dict[str, int] = {}
        self.pages_crawled: int = 0
        self.duplicate_count: int = 0
        self.last_progress_time: float = time.time()
        self.last_progress_pages: int = 0
        self.start_time: float = time.time()
        self.retry_counts: Dict[str, int] = {}

    def start_requests(self):
        """Generate initial Scrapy requests from seed URLs or query URL."""
        urls_to_crawl = []

        if self.seed_urls:
            urls_to_crawl = self.seed_urls
        else:
            parsed = urlparse(self.query)
            if parsed.scheme and parsed.netloc:
                urls_to_crawl = [self.query]

        if not urls_to_crawl:
            self.logger.error(
                "No valid URLs to crawl. Provide a URL or seed URLs. "
                "For keyword search, use 'werdeep discover' instead."
            )
            return

        for url in urls_to_crawl:
            self.request_depth[url] = 1
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.errback_handler,
                meta={"depth": 1, "retry_count": 0},
                dont_filter=True,
            )

    def _is_whitelisted(self, url: str) -> bool:
        """Check if URL matches robots whitelist pattern.

        Args:
            url: URL to check.

        Returns:
            True if URL matches whitelist pattern.
        """
        if not self.robots_whitelist:
            return False

        parsed = urlparse(url)
        path = parsed.path

        for pattern in self.robots_whitelist:
            if fnmatch.fnmatch(path, pattern):
                logger.info(f"ROBOTS_OVERRIDE: {path}")
                return True
        return False

    def _is_low_relevance(self, url: str) -> bool:
        """Check if URL matches low-relevance path patterns.

        Args:
            url: URL to check.

        Returns:
            True if URL matches low-relevance pattern.
        """
        if self.relevance_threshold == 0.0:
            return False

        parsed = urlparse(url)
        path = parsed.path.lower()

        for low_path in LOW_RELEVANCE_PATHS:
            if path.startswith(low_path.lower()) or low_path.lower() in path:
                return True
        return False

    def _should_crawl_url(self, url: str) -> tuple[bool, Optional[str]]:
        """Determine if URL should be crawled.

        Args:
            url: URL to check.

        Returns:
            Tuple of (should_crawl, reason).
        """
        if self.no_dedup:
            return True, None

        normalized = normalize_url(url)
        if normalized in self.visited_urls:
            self.duplicate_count += 1
            return False, "DUPLICATE"

        if self._is_low_relevance(url):
            logger.debug(f"LOW_RELEVANCE: {url}")
            return False, "LOW_RELEVANCE"

        return True, None

    def _emit_progress(self) -> None:
        """Emit progress update to stderr."""
        if self.quiet:
            return

        current_time = time.time()
        time_elapsed = current_time - self.last_progress_time
        pages_since_last = self.pages_crawled - self.last_progress_pages

        if time_elapsed >= PROGRESS_INTERVAL_SECONDS or pages_since_last >= PROGRESS_INTERVAL_PAGES:
            elapsed_total = current_time - self.start_time
            rate = self.pages_crawled / elapsed_total if elapsed_total > 0 else 0
            current_depth = max((r.depth for r in self.results), default=0)

            sys.stderr.write(
                f"[PROGRESS] Crawled {self.pages_crawled}/{self.max_pages} pages | "
                f"Depth: {current_depth} | Rate: {rate:.1f}/s\n"
            )
            sys.stderr.flush()

            self.last_progress_time = current_time
            self.last_progress_pages = self.pages_crawled

    def parse(self, response: Response):
        """Parse response and extract content.

        Args:
            response: Scrapy response object.
        """
        text_response = cast(TextResponse, response)
        if self.pages_crawled >= self.max_pages:
            self.logger.info(f"Max pages limit reached: {self.max_pages}")
            return

        url = response.url

        if not self.no_dedup:
            normalized = normalize_url(url)
            if normalized in self.visited_urls:
                return
            self.visited_urls.add(normalized)
        else:
            if url in self.visited_urls:
                return
            self.visited_urls.add(url)

        self.pages_crawled += 1
        self._emit_progress()

        depth = response.meta.get("depth", 1)
        retry_count = response.meta.get("retry_count", 0)

        self.logger.info(
            f"Crawling {url} at depth {depth} (page {self.pages_crawled}/{self.max_pages})"
        )

        content_length = len(response.body)
        if content_length > MAX_CONTENT_SIZE_BYTES:
            self.logger.warning(f"Content too large: {url} ({content_length} bytes)")
            return

        html = response.text
        text = self.parser.extract_text(html)
        title = self.parser.extract_title(html)
        links = self.parser.extract_links(html, url)
        code_blocks = self.parser.extract_code_blocks(html)

        content_keywords = self.content_analyzer.extract_keywords(text)
        content_type = self.content_analyzer.classify_content_type(text, url)
        link_relevance = self.content_analyzer.score_link_relevance(links, text)

        result = ResultItem(
            url=url,
            title=title,
            content=text,
            depth=depth,
            timestamp=datetime.now(timezone.utc).isoformat(),
            links=links,
            metadata={
                "content_length": content_length,
                "markdown_length": len(text.encode("utf-8")) if text else 0,
                "retry_count": retry_count,
                "code_block_count": len(code_blocks),
            },
            code_blocks=code_blocks,
            content_keywords=content_keywords,
            content_type=content_type,
            outgoing_link_relevance=link_relevance,
        )

        self.results.append(result)

        if self.duplicate_count > DUPLICATE_WARNING_THRESHOLD:
            logger.warning(
                f"DUPLICATE_LINKS: {self.duplicate_count} duplicate URLs detected; "
                "consider refining source"
            )

        if depth < self.max_depth:
            is_multi_seed = len(self.seed_urls) > 1
            if is_multi_seed:
                link_extractor = LinkExtractor()
            else:
                link_extractor = LinkExtractor(allow_domains=[urlparse(url).netloc])

            extracted_links = link_extractor.extract_links(text_response)

            if self.deterministic:
                extracted_links = sorted(extracted_links, key=lambda l: l.url)

            for link in extracted_links:
                next_url = link.url

                should_crawl, reason = self._should_crawl_url(next_url)
                if not should_crawl:
                    continue

                next_depth = depth + 1
                if next_depth <= self.max_depth:
                    self.request_depth[next_url] = next_depth

                    yield scrapy.Request(
                        url=next_url,
                        callback=self.parse,
                        errback=self.errback_handler,
                        meta={"depth": next_depth, "retry_count": 0},
                    )

    def errback_handler(self, failure):
        """Handle request errors with retry logic.

        Args:
            failure: Twisted failure object.
        """
        request = failure.request
        url = request.url
        retry_count = request.meta.get("retry_count", 0)

        if hasattr(failure.value, "response"):
            status = getattr(failure.value.response, "status", None)
        else:
            status = None

        if status and status in RETRY_STATUS_CODES and retry_count < self.max_retries:
            next_retry = retry_count + 1
            delay = self.retry_delay * (2**retry_count)

            logger.debug(
                f"Retrying {url} (attempt {next_retry}/{self.max_retries}) "
                f"after {delay}s delay (status: {status})"
            )

            time.sleep(delay)

            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.errback_handler,
                meta={
                    "depth": request.meta.get("depth", 1),
                    "retry_count": next_retry,
                },
            )
        else:
            if status:
                self.logger.error(f"Error crawling {url}: HTTP {status}")
            else:
                self.logger.error(f"Error crawling {url}: {failure.value}")

    def get_results(self) -> list[ResultItem]:
        """Get all crawled results.

        Returns:
            List of ResultItem objects.
        """
        return self.results

    def get_pages_crawled(self) -> int:
        """Get total pages crawled.

        Returns:
            Number of pages successfully crawled.
        """
        return self.pages_crawled

    def get_max_depth_achieved(self) -> int:
        """Get maximum depth achieved.

        Returns:
            Maximum depth reached during crawl.
        """
        if not self.results:
            return 0
        return max(r.depth for r in self.results)

    def get_duplicate_count(self) -> int:
        """Get duplicate URL count.

        Returns:
            Number of duplicate URLs skipped.
        """
        return self.duplicate_count
