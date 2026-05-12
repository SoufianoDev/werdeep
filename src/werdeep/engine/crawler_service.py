"""Crawler service for WeRDeep.

This module provides the service layer that orchestrates
both discovery (search) and crawling operations.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from scrapy.crawler import CrawlerProcess
from scrapy.signals import spider_closed

from werdeep.config.settings import (
    DEFAULT_CONCURRENT_REQUESTS,
    DEFAULT_DDGS_BACKEND,
    DEFAULT_DISCOVERY_MAX_WORKERS,
    DEFAULT_MAX_SEARCH_RESULTS,
    DEFAULT_SEARCH_ENGINES,
    DEFAULT_SEARCH_TIMEOUT,
    ENGINE_COOLDOWN_SECONDS,
    MAX_CONTENT_SIZE_BYTES,
    USER_AGENT,
)
from werdeep.config.ssl_bootstrap import get_ca_bundle
from werdeep.engine.crawler import WeRDeepSpider
from werdeep.engine.exceptions import WeRDeepError
from werdeep.engine.models import (
    ErrorInfo,
    Metadata,
    ResultItem,
    SearchRequest,
    SearchResult,
)
from werdeep.search.contracts import (
    DiscoveryMetadata,
    DiscoveryReport,
    SearchQuery,
    SearchResultItem,
)
from werdeep.search.engines import create_engine

logger = logging.getLogger(__name__)

_NPMJS_PATTERN = re.compile(r"https?://(?:www\.)?npmjs\.com/package/([^/?#]+)")


class CrawlerService:
    """Service for executing web crawling and discovery requests.

    This service manages the lifecycle of both discovery (search)
    and crawl sessions, including starting the crawler, collecting
    results, and handling errors.
    """

    def __init__(self) -> None:
        """Initialize crawler service."""
        self._results: list[ResultItem] = []

    def discover(
        self,
        query: str,
        *,
        domains: Optional[list[str]] = None,
        engines: Optional[list[str]] = None,
        max_results: int = DEFAULT_MAX_SEARCH_RESULTS,
        timeout: int = DEFAULT_SEARCH_TIMEOUT,
        backend: str = DEFAULT_DDGS_BACKEND,
        query_delay_ms: int = 0,
        cooldown_seconds: int = ENGINE_COOLDOWN_SECONDS,
    ) -> DiscoveryReport:
        """Execute a discovery (search) request.

        Queries multiple search engines and returns structured
        results with signals for agent decision-making.

        Args:
            query: Search query string.
            domains: Optional domain list for site: filtering.
            engines: Engine names to use.
            max_results: Maximum results to return.
            timeout: Per-engine timeout in seconds.
            backend: ddgs backend selection (e.g., "auto", "bing,brave,google").
            query_delay_ms: Milliseconds to delay between sequential queries.
            cooldown_seconds: Seconds an engine stays in cooldown after failure.

        Returns:
            DiscoveryReport with discovered URLs and signals.
        """
        try:
            engine_names = engines or DEFAULT_SEARCH_ENGINES
            engine_instances = [
                create_engine(name, timeout=timeout, backend=backend) for name in engine_names
            ]

            from werdeep.search.discovery import SearchDiscovery

            discovery = SearchDiscovery(
                engines=engine_instances,
                max_workers=DEFAULT_DISCOVERY_MAX_WORKERS,
                query_delay_ms=query_delay_ms,
                cooldown_seconds=cooldown_seconds,
            )
            search_query = SearchQuery(
                text=query,
                domains=tuple(domains) if domains else (),
                max_results=max_results,
                timeout=timeout,
            )
            report = discovery.search(search_query)

            if report.results:
                rewritten_items = []
                for item in report.results:
                    rewritten_url = self._rewrite_npmjs_url(item.url)
                    if rewritten_url != item.url:
                        rewritten_items.append(
                            SearchResultItem(
                                url=rewritten_url,
                                title=item.title,
                                snippet=item.snippet,
                                source_engine=item.source_engine,
                                source_domains=item.source_domains,
                                rank=item.rank,
                                relevance_score=item.relevance_score,
                                cross_engine=item.cross_engine,
                            )
                        )
                    else:
                        rewritten_items.append(item)

                new_metadata = DiscoveryMetadata(
                    query=report.metadata.query,
                    domains=report.metadata.domains,
                    engines_used=report.metadata.engines_used,
                    engines_failed=report.metadata.engines_failed,
                    total_results=len(rewritten_items),
                    duration_ms=report.metadata.duration_ms,
                    engine_errors=report.metadata.engine_errors,
                )

                report = DiscoveryReport(
                    status=report.status,
                    query=report.query,
                    results=tuple(rewritten_items),
                    metadata=new_metadata,
                    error=report.error,
                )

            return report
        except Exception as e:
            logger.error(f"Discovery failed: {e}", exc_info=True)
            return DiscoveryReport(
                status="error",
                query=query,
                results=(),
                metadata=DiscoveryMetadata(
                    query=query,
                    domains=tuple(domains) if domains else (),
                    engines_used=(),
                    engines_failed=(),
                    total_results=0,
                    duration_ms=0,
                ),
                error=str(e),
            )

    def run(self, request: SearchRequest) -> SearchResult:
        """Execute a crawling request.

        Args:
            request: Search request with query/URLs and parameters.

        Returns:
            SearchResult with crawled content or error.

        Raises:
            WeRDeepError: If crawling fails critically.
        """
        timestamp_start = datetime.now(timezone.utc).isoformat()
        start_time = datetime.now(timezone.utc)

        try:
            from urllib.parse import urlparse

            seed_urls = request.seed_urls
            if not seed_urls:
                parsed = urlparse(request.query)
                if parsed.scheme and parsed.netloc:
                    seed_urls = [request.query]

            if seed_urls:
                seed_urls = [self._rewrite_npmjs_url(u) for u in seed_urls]

            is_url_based = bool(seed_urls)

            settings = {
                "USER_AGENT": USER_AGENT,
                "CONCURRENT_REQUESTS": DEFAULT_CONCURRENT_REQUESTS,
                "DOWNLOAD_TIMEOUT": request.timeout,
                "LOG_LEVEL": "ERROR",
                "TELNETCONSOLE_ENABLED": False,
                "ROBOTSTXT_OBEY": is_url_based,
                "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
            }

            ca_bundle = get_ca_bundle()
            if ca_bundle:
                settings["REQUESTS_CA_BUNDLE"] = ca_bundle

            if request.robots_whitelist:
                settings["ROBOTSTXT_OBEY"] = False

            results, duplicate_count = self._run_crawler_sync(request, settings, seed_urls)

            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            timestamp_end = end_time.isoformat()

            total_size = sum(len(r.content.encode("utf-8")) for r in results)
            if total_size > MAX_CONTENT_SIZE_BYTES * request.max_pages:
                logger.warning(
                    f"Total content size {total_size} bytes exceeds limit. "
                    f"Consider reducing max_pages parameter."
                )

            max_depth_achieved = max((r.depth for r in results), default=0)

            metadata = Metadata(
                depth_achieved=max_depth_achieved,
                pages_crawled=len(results),
                duration_ms=duration_ms,
                format=request.format,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                duplicate_count=duplicate_count,
            )

            search_result = SearchResult(
                status="success",
                query=request.query,
                results=results,
                metadata=metadata,
            )

            logger.info(
                f"Crawl completed: {len(results)} pages, "
                f"depth {max_depth_achieved}, {duration_ms}ms"
            )

            return search_result

        except WeRDeepError:
            raise

        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)

            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            timestamp_end = end_time.isoformat()

            metadata = Metadata(
                depth_achieved=0,
                pages_crawled=0,
                duration_ms=duration_ms,
                format=request.format,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                duplicate_count=0,
            )

            return SearchResult(
                status="error",
                query=request.query,
                results=[],
                metadata=metadata,
                error=ErrorInfo(
                    code="INTERNAL_ERROR",
                    message=str(e),
                    action="Please try again or contact support",
                ),
            )

    def _run_crawler_sync(
        self,
        request: SearchRequest,
        settings: dict,
        seed_urls: Optional[list[str]] = None,
    ) -> tuple[list[ResultItem], int]:
        """Run crawler synchronously.

        Args:
            request: Search request.
            settings: Scrapy settings.
            seed_urls: List of seed URLs to crawl.

        Returns:
            Tuple of (list of ResultItem objects, duplicate count).
        """
        spider_cls = WeRDeepSpider

        class ResultsCollector:
            def __init__(self):
                self.results: list[ResultItem] = []
                self.duplicate_count: int = 0

            def collect(self, spider):
                if hasattr(spider, "get_results"):
                    self.results.extend(spider.get_results())
                if hasattr(spider, "get_duplicate_count"):
                    self.duplicate_count = spider.get_duplicate_count()

        collector = ResultsCollector()

        process = CrawlerProcess(settings)
        crawler = process.create_crawler(spider_cls)

        crawler.signals.connect(collector.collect, signal=spider_closed)

        process.crawl(
            crawler,
            query=request.query,
            seed_urls=seed_urls or [],
            max_depth=request.depth,
            max_pages=request.max_pages,
            timeout=request.timeout,
            relevance_threshold=request.relevance_threshold,
            robots_whitelist=request.robots_whitelist,
            max_retries=request.max_retries,
            retry_delay=request.retry_delay,
            quiet=request.quiet,
            no_dedup=request.no_dedup,
            deterministic=request.deterministic,
        )

        process.start()

        return collector.results, collector.duplicate_count

    def stop(self) -> None:
        """Stop the crawler if running."""
        logger.info("Stopping crawler")

    @staticmethod
    def _rewrite_npmjs_url(url: str) -> str:
        """Rewrite npmjs.com URLs to use the npm registry API.

        npmjs.com blocks automated scraping (403 Forbidden), but
        registry.npmjs.org is a free public JSON API that requires
        no API keys.

        Example:
            https://www.npmjs.com/package/react-toastify
            -> https://registry.npmjs.org/react-toastify
        """
        match = _NPMJS_PATTERN.match(url)
        if match:
            package_name = match.group(1)
            rewritten = f"https://registry.npmjs.org/{package_name}"
            logger.info(f"Rewrote npmjs URL: {url} -> {rewritten}")
            return rewritten
        return url
