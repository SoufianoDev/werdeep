"""CLI entry point for WeRDeep.

This module provides the command-line interface for invoking
WeRDeep as a subprocess from OpenCode tool wrappers and
LLM agent environments. Supports two modes: discover (search)
and crawl (deep extraction).
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests

from werdeep.config.settings import (
    DEFAULT_DDGS_BACKEND,
    DEFAULT_DEPTH,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_SEARCH_RESULTS,
    DEFAULT_RELEVANCE_THRESHOLD,
    DEFAULT_RETRY_DELAY,
    DEFAULT_SEARCH_ENGINES,
    DEFAULT_SEARCH_TIMEOUT,
    DEFAULT_TIMEOUT,
    ENGINE_COOLDOWN_SECONDS,
    MAX_DEPTH,
    MAX_PAGES_LIMIT,
    MAX_TIMEOUT,
    MIN_DEPTH,
    MIN_PAGES,
    MIN_TIMEOUT,
    URL_VALIDATION_TIMEOUT,
    VALID_OUTPUT_FORMATS,
)
from werdeep.config.ssl_bootstrap import get_ca_bundle
from werdeep.engine.exceptions import InvalidURLError, UnreachableURLError, WeRDeepError
from werdeep.engine.models import ErrorInfo, Metadata, SearchResult


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for WeRDeep CLI."""
    parser = argparse.ArgumentParser(
        prog="werdeep",
        description="Deep web search and research tool for OpenCode",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    _add_discover_parser(subparsers)
    _add_crawl_parser(subparsers)

    return parser


def _add_discover_parser(subparsers) -> None:
    """Add the discover subcommand parser."""
    discover_parser = subparsers.add_parser(
        "discover",
        help="Search for URLs related to a query using multiple search engines",
    )
    discover_parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query to discover URLs for (optional if --config is used)",
    )
    discover_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=(
            "Path to JSON config file (agent payload). When provided, all other args are ignored."
        ),
    )
    discover_parser.add_argument(
        "--engines",
        type=str,
        default=",".join(DEFAULT_SEARCH_ENGINES),
        help=(f"Comma-separated search engines (default: {','.join(DEFAULT_SEARCH_ENGINES)})"),
    )
    discover_parser.add_argument(
        "--domains",
        type=str,
        default="",
        help=("Comma-separated domains for site: filtering (e.g., github.com,stackoverflow.com)"),
    )
    discover_parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_SEARCH_RESULTS,
        help=f"Maximum results to return (default: {DEFAULT_MAX_SEARCH_RESULTS})",
    )
    discover_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_SEARCH_TIMEOUT,
        help=f"Per-engine timeout in seconds (default: {DEFAULT_SEARCH_TIMEOUT})",
    )
    discover_parser.add_argument(
        "--format",
        choices=VALID_OUTPUT_FORMATS,
        default="json",
        help="Output format (default: json)",
    )
    discover_parser.add_argument(
        "--backend",
        type=str,
        default=DEFAULT_DDGS_BACKEND,
        help=(
            f"ddgs search backend(s) (default: {DEFAULT_DDGS_BACKEND}). "
            "Options: auto, bing, brave, duckduckgo, google, yahoo, mojeek, yandex. "
            "Comma-delimit for multi-backend (e.g., bing,brave,google)."
        ),
    )
    discover_parser.add_argument(
        "--query-delay",
        type=int,
        default=0,
        help=("Milliseconds to delay between sequential queries in a session (default: 0)"),
    )
    discover_parser.add_argument(
        "--cooldown",
        type=int,
        default=ENGINE_COOLDOWN_SECONDS,
        help=(
            f"Seconds an engine stays in cooldown after failure "
            f"(default: {ENGINE_COOLDOWN_SECONDS})"
        ),
    )


def _add_crawl_parser(subparsers) -> None:
    """Add the crawl subcommand parser."""
    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Deep crawl one or more URLs and extract content",
    )
    crawl_parser.add_argument(
        "urls",
        nargs="+",
        help="One or more URLs to crawl",
    )
    crawl_parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Original search query for content analysis context",
    )
    crawl_parser.add_argument(
        "--format",
        choices=VALID_OUTPUT_FORMATS,
        default="json",
        help="Output format (default: json)",
    )
    crawl_parser.add_argument(
        "--depth",
        type=int,
        default=DEFAULT_DEPTH,
        help=f"Crawl depth {MIN_DEPTH}-{MAX_DEPTH} (default: {DEFAULT_DEPTH})",
    )
    crawl_parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=(
            f"Maximum pages to crawl {MIN_PAGES}-{MAX_PAGES_LIMIT} (default: {DEFAULT_MAX_PAGES})"
        ),
    )
    crawl_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds {MIN_TIMEOUT}-{MAX_TIMEOUT} (default: {DEFAULT_TIMEOUT})",
    )
    crawl_parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip URL pre-validation before crawling",
    )
    crawl_parser.add_argument(
        "--relevance-threshold",
        type=float,
        default=DEFAULT_RELEVANCE_THRESHOLD,
        help="Relevance filtering threshold 0.0-1.0 (default: 0.3)",
    )
    crawl_parser.add_argument(
        "--robots-whitelist",
        type=str,
        default="",
        help="Comma-separated path patterns to whitelist (e.g., /docs/*,/api/*)",
    )
    crawl_parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=(f"Maximum retry attempts for transient failures (default: {DEFAULT_MAX_RETRIES})"),
    )
    crawl_parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY,
        help=f"Base delay for retry backoff in seconds (default: {DEFAULT_RETRY_DELAY})",
    )
    crawl_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    crawl_parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable link deduplication",
    )
    crawl_parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Sort extracted links by URL for reproducible crawl results",
    )


def validate_url(url: str) -> None:
    """Validate URL structure and accessibility.

    Raises:
        InvalidURLError: If URL structure is invalid.
        UnreachableURLError: If URL is not accessible.
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        raise InvalidURLError(f"INVALID_URL: Missing scheme in URL: {url}")
    if not parsed.netloc:
        raise InvalidURLError(f"INVALID_URL: Missing netloc in URL: {url}")
    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(f"INVALID_URL: Invalid scheme '{parsed.scheme}' in URL: {url}")

    try:
        ca_bundle = get_ca_bundle()
        response = requests.head(
            url,
            timeout=URL_VALIDATION_TIMEOUT,
            allow_redirects=True,
            verify=ca_bundle if ca_bundle else True,
        )
        if response.status_code < 200 or response.status_code >= 400:
            raise UnreachableURLError(
                f"UNREACHABLE_URL: HTTP {response.status_code} for URL: {url}"
            )
    except requests.exceptions.Timeout:
        raise UnreachableURLError(f"UNREACHABLE_URL: Connection timeout for URL: {url}")
    except requests.exceptions.ConnectionError as e:
        raise UnreachableURLError(f"UNREACHABLE_URL: Connection error for URL: {url} - {e}")
    except requests.exceptions.RequestException as e:
        raise UnreachableURLError(f"UNREACHABLE_URL: Request failed for URL: {url} - {e}")


def _run_discover(args) -> int:
    """Execute the discover subcommand."""
    from werdeep.engine.crawler_service import CrawlerService
    from werdeep.engine.models import Metadata, SearchResult
    from werdeep.search.contracts import SearchQuery

    timestamp_start = datetime.now(timezone.utc).isoformat()

    try:
        service = CrawlerService()

        if args.config:
            search_query = SearchQuery.from_json(args.config)

            with open(args.config, encoding="utf-8") as f:
                config_data = json.load(f)
            engines = config_data.get("engines")

            result = service.discover(
                query=search_query.text,
                domains=list(search_query.domains) if search_query.domains else None,
                engines=engines,
                max_results=search_query.max_results,
                timeout=search_query.timeout,
                backend=config_data.get("backend", DEFAULT_DDGS_BACKEND),
                query_delay_ms=config_data.get("query_delay_ms", 0),
                cooldown_seconds=config_data.get("cooldown_seconds", ENGINE_COOLDOWN_SECONDS),
            )
        else:
            if not args.query:
                print(
                    "Error: query argument is required when --config is not used",
                    file=sys.stderr,
                )
                return 1

            engines = [e.strip() for e in args.engines.split(",") if e.strip()]
            domains = (
                [d.strip() for d in args.domains.split(",") if d.strip()] if args.domains else None
            )

            result = service.discover(
                query=args.query,
                domains=domains,
                engines=engines,
                max_results=args.max_results,
                timeout=args.timeout,
                backend=getattr(args, "backend", DEFAULT_DDGS_BACKEND),
                query_delay_ms=getattr(args, "query_delay", 0),
                cooldown_seconds=getattr(args, "cooldown", ENGINE_COOLDOWN_SECONDS),
            )

        output = _format_discovery_result(result, args.format)
        print(output)
        return 0

    except Exception as e:
        timestamp_end = datetime.now(timezone.utc).isoformat()
        error_result = SearchResult(
            status="error",
            query=args.query or "",
            results=[],
            metadata=Metadata(
                depth_achieved=0,
                pages_crawled=0,
                duration_ms=0,
                format=args.format,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
            ),
            error=ErrorInfo(
                code="INTERNAL_ERROR",
                message=str(e),
                action="Please try again or contact support",
            ),
        )
        print(json.dumps(asdict(error_result), indent=2))
        return 1


def _run_crawl(args) -> int:
    """Execute the crawl subcommand."""
    from werdeep.engine.crawler_service import CrawlerService
    from werdeep.engine.formatter import Formatter
    from werdeep.engine.models import SearchRequest

    timestamp_start = datetime.now(timezone.utc).isoformat()

    try:
        if not args.skip_validation:
            for url in args.urls:
                try:
                    validate_url(url)
                except (InvalidURLError, UnreachableURLError) as e:
                    timestamp_end = datetime.now(timezone.utc).isoformat()
                    error_result = SearchResult(
                        status="error",
                        query=url,
                        results=[],
                        metadata=Metadata(
                            depth_achieved=0,
                            pages_crawled=0,
                            duration_ms=0,
                            format=args.format,
                            timestamp_start=timestamp_start,
                            timestamp_end=timestamp_end,
                        ),
                        error=ErrorInfo(
                            code=e.code,
                            message=e.message,
                            action=e.action,
                        ),
                    )
                    print(json.dumps(asdict(error_result), indent=2))
                    return 1

        query = args.query or " ".join(args.urls)

        request = SearchRequest(
            query=query,
            format=args.format,
            depth=args.depth,
            max_pages=args.max_pages,
            timeout=args.timeout,
            skip_validation=args.skip_validation,
            relevance_threshold=args.relevance_threshold,
            robots_whitelist=args.robots_whitelist,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            quiet=args.quiet,
            no_dedup=args.no_dedup,
            seed_urls=args.urls,
            deterministic=args.deterministic,
        )

        service = CrawlerService()
        result = service.run(request)

        formatter = Formatter()
        formatted_output = formatter.format(result, args.format)

        print(formatted_output)
        return 0

    except WeRDeepError as e:
        timestamp_end = datetime.now(timezone.utc).isoformat()

        error_result = SearchResult(
            status="error",
            query=args.query or " ".join(args.urls),
            results=[],
            metadata=Metadata(
                depth_achieved=0,
                pages_crawled=0,
                duration_ms=0,
                format=args.format,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
            ),
            error=ErrorInfo(
                code=e.code,
                message=e.message,
                action=e.action,
            ),
        )

        print(json.dumps(asdict(error_result), indent=2))
        return 1

    except Exception as e:
        timestamp_end = datetime.now(timezone.utc).isoformat()

        error_result = SearchResult(
            status="error",
            query=args.query or " ".join(args.urls),
            results=[],
            metadata=Metadata(
                depth_achieved=0,
                pages_crawled=0,
                duration_ms=0,
                format=args.format,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
            ),
            error=ErrorInfo(
                code="INTERNAL_ERROR",
                message=str(e),
                action="Please try again or contact support",
            ),
        )

        print(json.dumps(asdict(error_result), indent=2))
        return 1


def _format_discovery_result(result, format_type: str) -> str:
    """Format a discovery result for output."""
    if format_type == "json":
        return _format_discovery_json(result)
    elif format_type == "markdown":
        return _format_discovery_markdown(result)
    elif format_type == "text":
        return _format_discovery_text(result)
    else:
        return _format_discovery_json(result)


def _format_discovery_json(result) -> str:
    """Format discovery result as JSON."""
    output = {
        "status": result.status,
        "query": result.query,
        "results": [
            {
                "url": item.url,
                "title": item.title,
                "snippet": item.snippet,
                "source_engine": item.source_engine,
                "source_domains": list(item.source_domains),
                "rank": item.rank,
                "relevance_score": item.relevance_score,
                "cross_engine": item.cross_engine,
            }
            for item in result.results
        ],
        "metadata": {
            "query": result.metadata.query,
            "domains": list(result.metadata.domains),
            "engines_used": list(result.metadata.engines_used),
            "engines_failed": list(result.metadata.engines_failed),
            "total_results": result.metadata.total_results,
            "duration_ms": result.metadata.duration_ms,
            "engine_errors": result.metadata.engine_errors,
        },
    }
    if result.error:
        output["error"] = result.error
    return json.dumps(output, indent=2)


def _format_discovery_markdown(result) -> str:
    """Format discovery result as Markdown."""
    lines = []
    lines.append("# WeRDeep Discovery Results")
    lines.append("")
    lines.append(f"**Query**: {result.query}")
    lines.append(f"**Status**: {result.status}")
    lines.append(f"**Engines Used**: {', '.join(result.metadata.engines_used)}")
    lines.append(f"**Domains**: {', '.join(result.metadata.domains) or '(none)'}")
    lines.append(f"**Total Results**: {result.metadata.total_results}")
    lines.append(f"**Duration**: {result.metadata.duration_ms}ms")
    lines.append("")

    if result.status == "error":
        lines.append("## Error")
        lines.append("")
        lines.append(f"**Message**: {result.error}")
        lines.append("")
        return "\n".join(lines)

    if result.status == "partial":
        lines.append("## Partial Results")
        lines.append("")
        lines.append(f"**Warning**: {result.error}")
        lines.append("")

    lines.append("## Discovered URLs")
    lines.append("")

    for idx, item in enumerate(result.results, 1):
        cross = " [cross-engine]" if item.cross_engine else ""
        lines.append(f"### {idx}. {item.title}{cross}")
        lines.append("")
        lines.append(f"**URL**: {item.url}")
        lines.append(f"**Relevance**: {item.relevance_score:.2f}")
        lines.append(f"**Source**: {item.source_engine}")
        if item.source_domains:
            lines.append(f"**Domains**: {', '.join(item.source_domains)}")
        if item.snippet:
            lines.append(f"**Snippet**: {item.snippet}")
        lines.append("")

    return "\n".join(lines)


def _format_discovery_text(result) -> str:
    """Format discovery result as plain text."""
    lines = []
    lines.append("=" * 80)
    lines.append("WERDEEP DISCOVERY RESULTS")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Query: {result.query}")
    lines.append(f"Status: {result.status}")
    lines.append(f"Engines Used: {', '.join(result.metadata.engines_used)}")
    lines.append(f"Domains: {', '.join(result.metadata.domains) or '(none)'}")
    lines.append(f"Total Results: {result.metadata.total_results}")
    lines.append(f"Duration: {result.metadata.duration_ms}ms")
    lines.append("")

    if result.status == "error":
        lines.append(f"ERROR: {result.error}")
        lines.append("")
        return "\n".join(lines)

    if result.status == "partial":
        lines.append(f"WARNING: {result.error}")
        lines.append("")

    lines.append("DISCOVERED URLS:")
    lines.append("")

    for idx, item in enumerate(result.results, 1):
        cross = " [CROSS-ENGINE]" if item.cross_engine else ""
        lines.append(f"  {idx}. {item.title}{cross}")
        lines.append(f"     URL: {item.url}")
        lines.append(f"     Relevance: {item.relevance_score:.2f} | Source: {item.source_engine}")
        if item.snippet:
            lines.append(f"     Snippet: {item.snippet}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point for WeRDeep CLI."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 1

    if parsed_args.command == "discover":
        return _run_discover(parsed_args)
    elif parsed_args.command == "crawl":
        return _run_crawl(parsed_args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
