"""Custom exceptions for WeRDeep.

This module defines all custom exception classes used throughout
the WeRDeep system. Each exception follows the error schema defined
in contracts/output-schema.json.
"""

from typing import Optional


class WeRDeepError(Exception):
    """Base exception for all WeRDeep errors.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable error message.
        action: Suggested action to resolve.
    """

    def __init__(
        self, message: str, code: str = "INTERNAL_ERROR", action: Optional[str] = None
    ) -> None:
        """Initialize WeRDeep error.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
            action: Suggested action to resolve.
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action or "Please try again or contact support"

    def to_dict(self) -> dict:
        """Convert exception to dictionary format.

        Returns:
            Dictionary with code, message, and action fields.
        """
        return {
            "code": self.code,
            "message": self.message,
            "action": self.action,
        }


class NetworkTimeoutError(WeRDeepError):
    """Raised when a network connection times out."""

    def __init__(self, message: str = "Connection timed out") -> None:
        """Initialize network timeout error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="NETWORK_TIMEOUT",
            action="Check network connectivity or increase timeout",
        )


# Fixed: C-01
class InvalidURLError(WeRDeepError):
    """Raised when a URL is malformed or invalid."""

    def __init__(self, message: str = "Invalid URL provided") -> None:
        """Initialize invalid URL error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="INVALID_URL",
            action="Provide a valid URL with proper format (e.g., https://example.com)",
        )


# Fixed: C-01
class UnreachableURLError(WeRDeepError):
    """Raised when a URL cannot be reached (network error, 4xx/5xx status)."""

    def __init__(self, message: str = "URL is unreachable") -> None:
        """Initialize unreachable URL error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="UNREACHABLE_URL",
            action=(
                "Check if the URL is accessible in a browser, or use --skip-validation to bypass"
            ),
        )


class BlockedBySiteError(WeRDeepError):
    """Raised when the target site blocks automated requests."""

    def __init__(self, message: str = "Site blocked automated requests") -> None:
        """Initialize blocked by site error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="BLOCKED_BY_SITE",
            action="Try a different URL or reduce request frequency",
        )


class RateLimitedError(WeRDeepError):
    """Raised when rate limiting is detected."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        """Initialize rate limited error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="RATE_LIMITED",
            action="Wait before making additional requests",
        )


class ContentTooLargeError(WeRDeepError):
    """Raised when content exceeds size limits."""

    def __init__(self, message: str = "Content size exceeds limit") -> None:
        """Initialize content too large error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="CONTENT_TOO_LARGE",
            action="Reduce max_pages or skip this URL",
        )


class ValidationError(WeRDeepError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        """Initialize validation error.

        Args:
            message: Human-readable error message.
            field: Field that failed validation.
        """
        super().__init__(
            message=message,
            code="INVALID_QUERY",
            action=f"Provide valid input for {field}" if field else "Provide valid input",
        )


class NetworkError(WeRDeepError):
    """Raised when a general network error occurs."""

    def __init__(self, message: str = "Network error occurred") -> None:
        """Initialize network error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="NETWORK_ERROR",
            action="Check internet connection and try again",
        )


class MaxPagesExceededError(WeRDeepError):
    """Raised when max pages limit is exceeded."""

    def __init__(self, message: str = "Maximum pages limit exceeded") -> None:
        """Initialize max pages exceeded error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="MAX_PAGES_EXCEEDED",
            action="Reduce max_pages parameter or narrow your search",
        )


class PermissionDeniedError(WeRDeepError):
    """Raised when permission is denied for an operation."""

    def __init__(self, message: str = "Permission denied") -> None:
        """Initialize permission denied error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            action="Check file permissions or installation mode",
        )


class CaptchaBlockedError(WeRDeepError):
    """Raised when a CAPTCHA challenge blocks the request."""

    def __init__(self, message: str = "CAPTCHA challenge detected") -> None:
        """Initialize CAPTCHA blocked error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(
            message=message,
            code="CAPTCHA_BLOCKED",
            action="Wait and retry later, or switch to a different search backend",
        )
