"""Content analysis module for WeRDeep.

This module provides the ContentAnalyzer class that extracts signals
from crawled content for agent decision-making. Signals include:
- content_keywords: Top extracted keywords/topics
- content_type: Classification of content type
- outgoing_link_relevance: Relevance scores for outgoing links
"""

import logging
import re
from collections import Counter
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "it",
        "as",
        "be",
        "was",
        "were",
        "been",
        "are",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "because",
        "if",
        "then",
        "else",
        "also",
        "about",
        "up",
        "out",
        "into",
        "over",
        "after",
        "before",
        "between",
        "under",
        "again",
        "further",
        "once",
        "here",
        "there",
        "any",
        "many",
        "much",
        "get",
        "got",
        "like",
        "new",
        "one",
        "two",
        "first",
        "last",
        "long",
        "great",
        "little",
        "just",
        "back",
        "still",
        "well",
        "way",
        "thing",
        "make",
        "take",
        "come",
        "know",
        "see",
        "look",
        "think",
        "give",
        "use",
        "find",
        "tell",
        "ask",
        "work",
        "seem",
        "feel",
        "try",
        "leave",
        "call",
        "keep",
        "let",
        "begin",
        "show",
        "hear",
        "play",
        "run",
        "move",
        "need",
        "put",
        "end",
    }
)

CONTENT_TYPE_PATTERNS = {
    "documentation": [
        r"(?i)(docs|documentation|reference|api\s*reference|user\s*guide)",
        r"(?i)(readme|getting\s+started|quick\s*start|installation\s*guide)",
        r"(?i)(parameters?|arguments?|return\s*value|examples?|syntax)",
    ],
    "code": [
        r"(?i)(github\.com|gitlab\.com|bitbucket\.org)",
        r"(?i)(repository|commit|pull\s*request|branch|merge|issue)",
        r"(?i)(function|class|method|import|def |const |var |let )",
    ],
    "qanda": [
        r"(?i)(stackoverflow\.com|stackexchange\.com|askubuntu\.com)",
        r"(?i)(question|answer|accepted\s*answer|upvote|downvote)",
        r"(?i)(q&a|frequently\s*asked|faq)",
    ],
    "discussion": [
        r"(?i)(reddit\.com|news\.ycombinator\.com|discourse|forum)",
        r"(?i)(comment|reply|thread|post|op\s*said|edit:)",
        r"(?i)(upvoted|downvoted|karma|subreddit)",
    ],
    "article": [
        r"(?i)(published|author|updated|reading\s*time|share\s*this)",
        r"(?i)(blog|article|opinion|editorial|tutorial)",
        r"(?i)(abstract|summary|conclusion|introduction|background)",
    ],
}

HIGH_RELEVANCE_DOMAINS = {
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "stackoverflow.com",
    "stackexchange.com",
    "askubuntu.com",
    "docs.python.org",
    "readthedocs.io",
    "developer.mozilla.org",
    "realpython.com",
    "medium.com",
    "dev.to",
}

LOW_RELEVANCE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".woff",
    ".woff2",
    ".ttf",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
}

LOW_RELEVANCE_PATHS = {
    "/login",
    "/signup",
    "/register",
    "/auth",
    "/privacy",
    "/terms",
    "/legal",
    "/about",
    "/contact",
    "/feedback",
    "/survey",
}


class ContentAnalyzer:
    """Analyzes crawled content and extracts signals for agent decision-making.

    This class provides methods for:
    - Extracting keywords/topics from text content
    - Classifying content type (article, documentation, code, etc.)
    - Scoring outgoing link relevance
    """

    def __init__(self, query: Optional[str] = None) -> None:
        """Initialize content analyzer.

        Args:
            query: Original search query for relevance scoring context.
        """
        self.query = query
        self._query_terms = self._extract_terms(query) if query else []

    def extract_keywords(self, text: str, max_keywords: int = 10) -> list[str]:
        """Extract top keywords from text content.

        Uses frequency analysis with stop word filtering.

        Args:
            text: Content text to analyze.
            max_keywords: Maximum number of keywords to return.

        Returns:
            List of keyword strings, ordered by relevance.
        """
        if not text:
            return []

        terms = self._extract_terms(text)
        if not terms:
            return []

        counter = Counter(terms)
        filtered = {
            term: count
            for term, count in counter.items()
            if term.lower() not in STOP_WORDS and len(term) > 2 and count > 1
        }

        if self._query_terms:
            query_lower = set(t.lower() for t in self._query_terms)
            boosted = {}
            for term, count in filtered.items():
                if term.lower() in query_lower:
                    boosted[term] = count * 2
                else:
                    boosted[term] = count
            filtered = boosted

        sorted_terms = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
        return [term for term, _ in sorted_terms[:max_keywords]]

    def classify_content_type(self, text: str, url: str = "") -> str:
        """Classify the type of content based on text and URL patterns.

        Args:
            text: Content text to analyze.
            url: Source URL for domain-based hints.

        Returns:
            Content type string: "article", "documentation", "code",
            "qanda", "discussion", or "reference".
        """
        if url:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            if domain in ("github.com", "gitlab.com", "bitbucket.org"):
                return "code"
            if domain in ("stackoverflow.com", "stackexchange.com", "askubuntu.com"):
                return "qanda"
            if domain in ("reddit.com", "news.ycombinator.com"):
                return "discussion"

        if not text:
            return "reference"

        combined = url + " " + text[:5000]

        scores: dict[str, int] = {}
        for content_type, patterns in CONTENT_TYPE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, combined)
                score += len(matches)
            scores[content_type] = score

        if not scores or max(scores.values()) == 0:
            return "article"

        return max(scores, key=lambda k: scores[k])

    def score_link_relevance(self, links: list[str], content_text: str = "") -> dict[str, float]:
        """Score outgoing links by relevance to the original query and content.

        Args:
            links: List of URLs to score.
            content_text: Page content text for context (optional).

        Returns:
            Dictionary mapping URL to relevance score (0.0-1.0).
        """
        if not links:
            return {}

        content_terms = set()
        if content_text:
            terms = self._extract_terms(content_text)
            content_terms = set(t.lower() for t in terms if t.lower() not in STOP_WORDS)

        scores: dict[str, float] = {}
        for link in links:
            score = self._score_single_link(link, content_terms)
            scores[link] = round(score, 3)

        return scores

    def _score_single_link(self, url: str, content_terms: set[str]) -> float:
        """Score a single link's relevance.

        Args:
            url: URL to score.
            content_terms: Set of content terms for context matching.

        Returns:
            Relevance score between 0.0 and 1.0.
        """
        score = 0.3

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            path = parsed.path.lower()

            if domain in HIGH_RELEVANCE_DOMAINS:
                score += 0.3

            _, ext = __import__("os").path.splitext(path)
            if ext.lower() in LOW_RELEVANCE_EXTENSIONS:
                return 0.0

            for low_path in LOW_RELEVANCE_PATHS:
                if path.startswith(low_path):
                    return 0.05

            path_parts = [p for p in path.split("/") if p]
            for part in path_parts:
                part_lower = part.lower().replace("-", " ").replace("_", " ")
                if content_terms and part_lower in content_terms:
                    score += 0.1

            if self._query_terms:
                for term in self._query_terms:
                    term_lower = term.lower()
                    if term_lower in url.lower():
                        score += 0.1

        except Exception:
            pass

        return min(1.0, score)

    @staticmethod
    def _extract_terms(text: str) -> list[str]:
        """Extract meaningful terms from text.

        Args:
            text: Input text.

        Returns:
            List of lowercased terms.
        """
        if not text:
            return []

        cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
        terms = cleaned.split()
        return [t for t in terms if len(t) > 1]
