"""Configuration constants for WeRDeep.

This module defines all configuration parameters and limits that
control WeRDeep's behavior. All values are named constants to
avoid magic numbers throughout the codebase.
"""

# Crawl Limits
DEFAULT_DEPTH: int = 3
DEFAULT_MAX_PAGES: int = 100
DEFAULT_TIMEOUT: int = 300
MAX_DEPTH: int = 5
MIN_DEPTH: int = 1
MAX_PAGES_LIMIT: int = 1000
MIN_PAGES: int = 1
MAX_CONTENT_SIZE_MB: int = 10
MAX_CONTENT_SIZE_BYTES: int = MAX_CONTENT_SIZE_MB * 1024 * 1024

# Network Settings
DEFAULT_CONCURRENT_REQUESTS: int = 5
DEFAULT_DOWNLOAD_TIMEOUT: int = 30
USER_AGENT: str = "WeRDeep/1.0"

# Fixed: C-01
# URL Validation Settings
URL_VALIDATION_TIMEOUT: int = 5

# Fixed: C-02
# Relevance Filtering
DEFAULT_RELEVANCE_THRESHOLD: float = 0.3
LOW_RELEVANCE_PATHS: list[str] = [
    "/brand/",
    "/codeofconduct/",
    "/legal/",
    "/privacy/",
    "/terms/",
    "/signup/",
    "/login/",
    "/feedback/",
    "/survey/",
    "/search",
]

# Fixed: H-02
# Retry Settings
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY: float = 1.0
RETRY_STATUS_CODES: list[int] = [429, 500, 502, 503, 504]

# Fixed: M-01
# Progress Settings
PROGRESS_INTERVAL_SECONDS: int = 5
PROGRESS_INTERVAL_PAGES: int = 10

# Fixed: M-02
# Deduplication Settings
DUPLICATE_WARNING_THRESHOLD: int = 10

# Output Format Options
OUTPUT_FORMAT_JSON: str = "json"
OUTPUT_FORMAT_MARKDOWN: str = "markdown"
OUTPUT_FORMAT_HTML: str = "html"
OUTPUT_FORMAT_TEXT: str = "text"
DEFAULT_FORMAT: str = OUTPUT_FORMAT_JSON
VALID_OUTPUT_FORMATS: list[str] = [
    OUTPUT_FORMAT_JSON,
    OUTPUT_FORMAT_MARKDOWN,
    OUTPUT_FORMAT_HTML,
    OUTPUT_FORMAT_TEXT,
]

# Validation Limits
MIN_TIMEOUT: int = 10
MAX_TIMEOUT: int = 3600

# Discovery Settings
DEFAULT_SEARCH_ENGINES: list[str] = ["ddgs"]
DEFAULT_SEARCH_TIMEOUT: int = 10
DEFAULT_MAX_SEARCH_RESULTS: int = 20
DEFAULT_DISCOVERY_MAX_WORKERS: int = 5
DEFAULT_DDGS_BACKEND: str = "auto"
DISCOVERY_QUERY_STAGGER_MS: int = 500
DISCOVERY_CACHE_MAX_SIZE: int = 50
DISCOVERY_CACHE_TTL_SECONDS: int = 300
ENGINE_COOLDOWN_SECONDS: int = 60

# Error Messages
ERROR_EMPTY_QUERY: str = "Query must not be empty"
ERROR_DEPTH_OUT_OF_RANGE: str = f"Depth must be between {MIN_DEPTH} and {MAX_DEPTH}"
ERROR_MAX_PAGES_OUT_OF_RANGE: str = f"Max pages must be between {MIN_PAGES} and {MAX_PAGES_LIMIT}"
ERROR_TIMEOUT_OUT_OF_RANGE: str = f"Timeout must be between {MIN_TIMEOUT} and {MAX_TIMEOUT}"
ERROR_INVALID_FORMAT: str = f"Format must be one of: {', '.join(VALID_OUTPUT_FORMATS)}"
