# cython: language_level=3
"""Content parsing and extraction module.

This module provides HTML parsing and content extraction
functionality for WeRDeep crawler.
"""

from bs4 import BeautifulSoup
from typing import List, Optional, Dict, Set
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

from werdeep.external.html_to_markdown import convert as html_to_md, ConversionOptions, PreprocessingOptions


class CodeBlock:
    """Represents a code block extracted from HTML.

    Attributes:
        type: Block type (code or diagram).
        language: Programming language or mermaid.
        content: Raw code content.
        syntax_highlighted: Whether original had highlighting.
    """

    def __init__(
        self,
        type: str = "code",
        language: Optional[str] = None,
        content: str = "",
        syntax_highlighted: bool = False,
    ):
        self.type = type
        self.language = language
        self.content = content
        self.syntax_highlighted = syntax_highlighted

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "language": self.language,
            "content": self.content,
            "syntax_highlighted": self.syntax_highlighted,
        }


class ContentParser:
    """Cython-based HTML content parser.

    This class provides methods for extracting text, links,
    and metadata from HTML content.
    """

    def __init__(self):
        self._seen_urls: Set[str] = set()
        self._md_options = ConversionOptions(
            heading_style="atx",
            code_block_style="backticks",
            bullets="-*+",
            strong_em_symbol="*",
            autolinks=True,
            strip_newlines=False,
            extract_metadata=False,
            skip_images=False,
            whitespace_mode="normalized",
            preprocessing=PreprocessingOptions(
                enabled=True,
                preset="aggressive",
                remove_navigation=True,
                remove_forms=True,
                remove_ads=True,
            ),
        )

    def extract_text(self, html: str) -> str:
        """Extract text content from HTML as structured markdown.

        Args:
            html: Raw HTML content.

        Returns:
            Extracted and cleaned markdown text content.
        """
        if not html:
            return ""

        result = html_to_md(html, options=self._md_options)
        return result.get("content") or ""

    def extract_title(self, html: str) -> Optional[str]:
        """Extract page title from HTML.

        Args:
            html: Raw HTML content.

        Returns:
            Page title or None if not found.
        """
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")

        if title_tag:
            return title_tag.get_text().strip()

        return None

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication.

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

    def extract_links(self, html: str, base_url: str, deduplicate: bool = True) -> List[str]:
        """Extract links from HTML.

        Args:
            html: Raw HTML content.
            base_url: Base URL for resolving relative links.
            deduplicate: Whether to deduplicate links.

        Returns:
            List of absolute URLs.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]

            absolute_url = urljoin(base_url, href)

            parsed = urlparse(absolute_url)
            if parsed.scheme in ("http", "https"):
                if deduplicate:
                    normalized = self._normalize_url(absolute_url)
                    if normalized not in seen:
                        seen.add(normalized)
                        links.append(absolute_url)
                else:
                    links.append(absolute_url)

        return links

    def extract_code_blocks(self, html: str) -> List[dict]:
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        code_blocks = []

        for pre in soup.find_all("pre"):
            code = pre.find("code")
            if code:
                language, syntax_highlighted = self._detect_language(code, pre)
                content = code.get_text()

                code_blocks.append(CodeBlock(
                    type="code",
                    language=language,
                    content=content,
                    syntax_highlighted=syntax_highlighted,
                ).to_dict())

            elif pre.get("class") and "mermaid" in pre.get("class", []):
                content = pre.get_text()
                code_blocks.append(CodeBlock(
                    type="diagram",
                    language="mermaid",
                    content=content,
                    syntax_highlighted=False,
                ).to_dict())

            else:
                content = pre.get_text()
                if content.strip():
                    language, syntax_highlighted = self._detect_language(pre, None)
                    code_blocks.append(CodeBlock(
                        type="code",
                        language=language,
                        content=content,
                        syntax_highlighted=syntax_highlighted,
                    ).to_dict())

        for div in soup.find_all("div"):
            if div.get("class") and "mermaid" in div.get("class", []):
                content = div.get_text()
                code_blocks.append(CodeBlock(
                    type="diagram",
                    language="mermaid",
                    content=content,
                    syntax_highlighted=False,
                ).to_dict())

        return code_blocks

    def _detect_language(self, code_or_pre, pre_parent=None) -> tuple:
        language = None
        syntax_highlighted = False

        for cls in code_or_pre.get("class", []):
            if cls.startswith("language-"):
                language = cls.replace("language-", "")
                syntax_highlighted = True
            elif cls.startswith("hljs"):
                syntax_highlighted = True
            elif cls == "highlight":
                syntax_highlighted = True
            elif cls.startswith("highlight-"):
                language = cls.replace("highlight-", "")
                syntax_highlighted = True

        if code_or_pre.get("data-language"):
            language = code_or_pre.get("data-language")
            syntax_highlighted = True

        if code_or_pre.get("data-lang"):
            language = code_or_pre.get("data-lang")
            syntax_highlighted = True

        if not language:
            language, syntax_highlighted = self._detect_language_from_ancestors(
                code_or_pre, pre_parent
            )

        return language, syntax_highlighted

    def _detect_language_from_ancestors(self, element, pre_parent=None, max_depth=3) -> tuple:
        """Walk up ancestor elements to detect language from MkDocs Material patterns.

        MkDocs Material uses patterns like:
        - <div class="highlight"><pre><code>
        - <div class="highlight-language-python">
        - <div data-lang="python">
        - <div class="codehilite">
        """
        language = None
        syntax_highlighted = False

        if pre_parent is not None:
            language, syntax_highlighted = self._check_element_language(pre_parent)
            if language:
                return language, syntax_highlighted

        parent = element.parent if hasattr(element, 'parent') else None
        depth = 0
        while parent is not None and depth < max_depth:
            lang, highlighted = self._check_element_language(parent)
            if lang:
                return lang, highlighted
            parent = parent.parent if hasattr(parent, 'parent') else None
            depth += 1

        return language, syntax_highlighted

    def _check_element_language(self, element) -> tuple:
        """Check a single element for language indicators."""
        language = None
        syntax_highlighted = False

        if element is None:
            return language, syntax_highlighted

        for cls in element.get("class", []):
            if cls.startswith("language-"):
                language = cls.replace("language-", "")
                syntax_highlighted = True
            elif cls.startswith("highlight-"):
                language = cls.replace("highlight-", "")
                syntax_highlighted = True
            elif cls in ("highlight", "codehilite"):
                syntax_highlighted = True

        if not language and element.get("data-language"):
            language = element.get("data-language")
            syntax_highlighted = True

        if not language and element.get("data-lang"):
            language = element.get("data-lang")
            syntax_highlighted = True

        return language, syntax_highlighted
