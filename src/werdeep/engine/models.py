"""Data models for WeRDeep.

This module defines all dataclasses that represent requests, results,
and metadata for the WeRDeep system. Models follow the structure
defined in data-model.md.
"""

from dataclasses import dataclass, field
from typing import Optional

from werdeep.config.settings import (
    DEFAULT_DEPTH,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RELEVANCE_THRESHOLD,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
    ERROR_DEPTH_OUT_OF_RANGE,
    ERROR_EMPTY_QUERY,
    ERROR_INVALID_FORMAT,
    ERROR_MAX_PAGES_OUT_OF_RANGE,
    ERROR_TIMEOUT_OUT_OF_RANGE,
    MAX_DEPTH,
    MAX_PAGES_LIMIT,
    MAX_TIMEOUT,
    MIN_DEPTH,
    MIN_PAGES,
    MIN_TIMEOUT,
    VALID_OUTPUT_FORMATS,
)

from .exceptions import ValidationError


@dataclass
class SearchRequest:
    """Represents a research query submitted to WeRDeep.

    Attributes:
        query: Keywords or topic description for content analysis context.
        format: Output format (json, markdown, html, text).
        depth: Crawl depth (1-5).
        max_pages: Maximum pages to crawl.
        timeout: Timeout in seconds.
        ai_postprocess: Enable AI post-processing.
        skip_validation: Skip URL pre-validation.
        relevance_threshold: Relevance filtering threshold (0.0-1.0).
        robots_whitelist: Comma-separated path patterns to whitelist.
        max_retries: Maximum retry attempts for transient failures.
        retry_delay: Base delay for retry backoff.
        quiet: Suppress progress output.
        no_dedup: Disable link deduplication.
        seed_urls: List of seed URLs to crawl (for crawl mode).
        engines: Search engines to use (for discover mode).
        domains: Domain list for site: filtering (for discover mode).
        max_discovery_results: Maximum discovery results (for discover mode).
    """

    query: str
    format: str = "json"
    depth: int = DEFAULT_DEPTH
    max_pages: int = DEFAULT_MAX_PAGES
    timeout: int = DEFAULT_TIMEOUT
    ai_postprocess: bool = False
    skip_validation: bool = False
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD
    robots_whitelist: str = ""
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    quiet: bool = False
    no_dedup: bool = False
    deterministic: bool = False
    seed_urls: list[str] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    max_discovery_results: int = 20

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate request parameters.

        Raises:
            ValidationError: If any parameter is invalid.
        """
        if not self.query or not self.query.strip():
            raise ValidationError(ERROR_EMPTY_QUERY, "query")

        if not (MIN_DEPTH <= self.depth <= MAX_DEPTH):
            raise ValidationError(ERROR_DEPTH_OUT_OF_RANGE, "depth")

        if not (MIN_PAGES <= self.max_pages <= MAX_PAGES_LIMIT):
            raise ValidationError(ERROR_MAX_PAGES_OUT_OF_RANGE, "max_pages")

        if not (MIN_TIMEOUT <= self.timeout <= MAX_TIMEOUT):
            raise ValidationError(ERROR_TIMEOUT_OUT_OF_RANGE, "timeout")

        if self.format not in VALID_OUTPUT_FORMATS:
            raise ValidationError(ERROR_INVALID_FORMAT, "format")

        if not (0.0 <= self.relevance_threshold <= 1.0):
            raise ValidationError(
                "Relevance threshold must be between 0.0 and 1.0", "relevance_threshold"
            )


@dataclass
class CodeBlock:
    """Represents a code block extracted from HTML.

    Attributes:
        type: Block type (code or diagram).
        language: Programming language or mermaid.
        content: Raw code content.
        syntax_highlighted: Whether original had highlighting.
    """

    type: str = "code"
    language: Optional[str] = None
    content: str = ""
    syntax_highlighted: bool = False


@dataclass
class ResultItem:
    """Represents a single crawled page.

    Attributes:
        url: Source URL.
        title: Page title.
        content: Extracted text content.
        depth: Crawl depth level (1 = seed).
        timestamp: ISO 8601 timestamp when page was fetched.
        links: Outgoing links found on page.
        metadata: Additional page metadata.
        code_blocks: Code blocks extracted from page.
        content_keywords: Top extracted keywords/topics for agent decision-making.
        content_type: Classification of content type (article, documentation, code, etc.).
        outgoing_link_relevance: Relevance scores for outgoing links {url: score}.
    """

    url: str
    content: str
    depth: int
    timestamp: str
    title: Optional[str] = None
    links: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    code_blocks: list[CodeBlock] = field(default_factory=list)
    content_keywords: list[str] = field(default_factory=list)
    content_type: str = "article"
    outgoing_link_relevance: dict[str, float] = field(default_factory=dict)


@dataclass
class Metadata:
    """Session-level metadata for tracking and analytics.

    Attributes:
        depth_achieved: Maximum depth reached.
        pages_crawled: Total pages processed.
        duration_ms: Total processing time in milliseconds.
        format: Output format used.
        timestamp_start: ISO 8601 start timestamp.
        timestamp_end: ISO 8601 end timestamp.
        duplicate_count: Number of duplicate URLs skipped.
    """

    depth_achieved: int
    pages_crawled: int
    duration_ms: int
    format: str
    timestamp_start: str
    timestamp_end: str
    duplicate_count: int = 0


@dataclass
class ErrorInfo:
    """Structured error information for actionable feedback.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable error message.
        action: Suggested action to resolve.
    """

    code: str
    message: str
    action: str


@dataclass
class SearchResult:
    """Represents the output of a WeRDeep research session.

    Attributes:
        status: Execution status (success or error).
        query: Original query string.
        results: Array of crawled items (empty on error).
        metadata: Session metadata.
        error: Error details (only on error status).
    """

    status: str
    query: str
    metadata: Metadata
    results: list[ResultItem] = field(default_factory=list)
    error: Optional[ErrorInfo] = None

    def __post_init__(self) -> None:
        """Validate status after initialization."""
        if self.status not in ("success", "error", "partial"):
            raise ValueError(
                f"Invalid status: {self.status}. Must be 'success', 'error', or 'partial'"
            )
