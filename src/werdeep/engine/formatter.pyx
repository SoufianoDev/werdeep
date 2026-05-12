# cython: language_level=3
"""Output formatting module.

This module provides formatting functionality for WeRDeep
output in multiple formats: JSON, Markdown, HTML, and plain text.
"""

import json
from typing import List
from werdeep.engine.models import SearchResult, ResultItem


class Formatter:
    """Cython-based output formatter.

    Provides methods for formatting search results in
    different output formats.
    """

    def format_json(self, result: SearchResult) -> str:
        """Format result as JSON.

        Args:
            result: SearchResult to format.

        Returns:
            JSON string representation.
        """
        result_dict = {
            "status": result.status,
            "query": result.query,
            "results": [
                {
                    "url": r.url,
                    "title": r.title,
                    "content": r.content,
                    "depth": r.depth,
                    "timestamp": r.timestamp,
                    "links": r.links,
                    "metadata": r.metadata,
                    "code_blocks": [cb if isinstance(cb, dict) else cb.to_dict() for cb in r.code_blocks] if r.code_blocks else [],
                    "content_keywords": r.content_keywords if r.content_keywords else [],
                    "content_type": r.content_type if r.content_type else "article",
                    "outgoing_link_relevance": r.outgoing_link_relevance if r.outgoing_link_relevance else {},
                }
                for r in result.results
            ],
            "metadata": {
                "depth_achieved": result.metadata.depth_achieved,
                "pages_crawled": result.metadata.pages_crawled,
                "duration_ms": result.metadata.duration_ms,
                "format": result.metadata.format,
                "timestamp_start": result.metadata.timestamp_start,
                "timestamp_end": result.metadata.timestamp_end,
                "duplicate_count": getattr(result.metadata, "duplicate_count", 0),
            },
        }

        if result.error:
            result_dict["error"] = {
                "code": result.error.code,
                "message": result.error.message,
                "action": result.error.action,
            }

        return json.dumps(result_dict, indent=2)

    def format_markdown(self, result: SearchResult) -> str:
        """Format result as Markdown.

        Args:
            result: SearchResult to format.

        Returns:
            Markdown formatted string.
        """
        lines = []

        lines.append("# WeRDeep Search Results")
        lines.append("")
        lines.append(f"**Query**: {result.query}")
        lines.append(f"**Status**: {result.status}")
        lines.append(f"**Pages Crawled**: {result.metadata.pages_crawled}")
        lines.append(f"**Depth Achieved**: {result.metadata.depth_achieved}")
        lines.append(f"**Duration**: {result.metadata.duration_ms}ms")
        if hasattr(result.metadata, "duplicate_count") and result.metadata.duplicate_count > 0:
            lines.append(f"**Duplicate URLs Skipped**: {result.metadata.duplicate_count}")
        lines.append("")

        if result.status == "error":
            lines.append("## Error")
            lines.append("")
            lines.append(f"**Code**: {result.error.code}")
            lines.append(f"**Message**: {result.error.message}")
            lines.append(f"**Action**: {result.error.action}")
            lines.append("")
            return "\n".join(lines)

        lines.append("## Results")
        lines.append("")

        for idx, item in enumerate(result.results, 1):
            lines.append(f"### {idx}. {item.title or 'Untitled'}")
            lines.append("")
            lines.append(f"**URL**: {item.url}")
            lines.append(f"**Depth**: {item.depth}")
            lines.append(f"**Timestamp**: {item.timestamp}")
            if item.content_type:
                lines.append(f"**Content Type**: {item.content_type}")
            if item.content_keywords:
                lines.append(f"**Keywords**: {', '.join(item.content_keywords[:10])}")
            lines.append("")
            lines.append(item.content)
            lines.append("")

            if item.outgoing_link_relevance:
                lines.append("**Top Relevant Links**:")
                lines.append("")
                sorted_links = sorted(item.outgoing_link_relevance.items(), key=lambda x: x[1], reverse=True)[:5]
                for link, score in sorted_links:
                    lines.append(f"- [{score:.2f}] {link}")
                lines.append("")

            if item.links:
                lines.append("**Links Found**:")
                lines.append("")
                for link in item.links:
                    lines.append(f"- {link}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def format_html(self, result: SearchResult) -> str:
        """Format result as HTML.

        Args:
            result: SearchResult to format.

        Returns:
            HTML formatted string.
        """
        html_parts = []

        html_parts.append("<!DOCTYPE html>")
        html_parts.append("<html lang='en'>")
        html_parts.append("<head>")
        html_parts.append("<meta charset='UTF-8'>")
        html_parts.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
        html_parts.append(f"<title>WeRDeep Results: {result.query}</title>")
        html_parts.append("<style>")
        html_parts.append("body { font-family: Arial, sans-serif; margin: 20px; }")
        html_parts.append(".result { border: 1px solid #ccc; padding: 15px; margin: 15px 0; }")
        html_parts.append(".meta { color: #666; font-size: 0.9em; }")
        html_parts.append(".content { margin-top: 10px; }")
        html_parts.append(".links { margin-top: 10px; }")
        html_parts.append(".code-block { background: #f4f4f4; padding: 10px; margin: 10px 0; border-radius: 4px; }")
        html_parts.append(".code-block pre { margin: 0; white-space: pre-wrap; }")
        html_parts.append("</style>")
        html_parts.append("</head>")
        html_parts.append("<body>")

        html_parts.append("<h1>WeRDeep Search Results</h1>")
        html_parts.append("<div class='meta'>")
        html_parts.append(f"<p><strong>Query:</strong> {result.query}</p>")
        html_parts.append(f"<p><strong>Status:</strong> {result.status}</p>")
        html_parts.append(f"<p><strong>Pages Crawled:</strong> {result.metadata.pages_crawled}</p>")
        html_parts.append(f"<p><strong>Depth Achieved:</strong> {result.metadata.depth_achieved}</p>")
        html_parts.append(f"<p><strong>Duration:</strong> {result.metadata.duration_ms}ms</p>")
        if hasattr(result.metadata, "duplicate_count") and result.metadata.duplicate_count > 0:
            html_parts.append(f"<p><strong>Duplicate URLs Skipped:</strong> {result.metadata.duplicate_count}</p>")
        html_parts.append("</div>")

        if result.status == "error":
            html_parts.append("<div class='error'>")
            html_parts.append("<h2>Error</h2>")
            html_parts.append(f"<p><strong>Code:</strong> {result.error.code}</p>")
            html_parts.append(f"<p><strong>Message:</strong> {result.error.message}</p>")
            html_parts.append(f"<p><strong>Action:</strong> {result.error.action}</p>")
            html_parts.append("</div>")
        else:
            html_parts.append("<h2>Results</h2>")
            for idx, item in enumerate(result.results, 1):
                html_parts.append("<div class='result'>")
                html_parts.append(f"<h3>{idx}. {item.title or 'Untitled'}</h3>")
                html_parts.append("<div class='meta'>")
                html_parts.append(f"<p><strong>URL:</strong> <a href='{item.url}'>{item.url}</a></p>")
                html_parts.append(f"<p><strong>Depth:</strong> {item.depth}</p>")
                html_parts.append(f"<p><strong>Timestamp:</strong> {item.timestamp}</p>")
                html_parts.append("</div>")
                html_parts.append("<div class='content'>")
                html_parts.append(f"<p>{item.content}</p>")
                html_parts.append("</div>")

                if item.code_blocks:
                    html_parts.append("<div class='code-blocks'>")
                    html_parts.append("<p><strong>Code Blocks:</strong></p>")
                    for cb in item.code_blocks:
                        cb_dict = cb if isinstance(cb, dict) else cb.to_dict()
                        lang = cb_dict.get("language", "") or ""
                        html_parts.append(f"<div class='code-block'>")
                        if lang:
                            html_parts.append(f"<p><em>Language: {lang}</em></p>")
                        html_parts.append(f"<pre>{cb_dict.get('content', '')}</pre>")
                        html_parts.append("</div>")
                    html_parts.append("</div>")

                if item.links:
                    html_parts.append("<div class='links'>")
                    html_parts.append("<p><strong>Links Found:</strong></p>")
                    html_parts.append("<ul>")
                    for link in item.links:
                        html_parts.append(f"<li><a href='{link}'>{link}</a></li>")
                    html_parts.append("</ul>")
                    html_parts.append("</div>")

                html_parts.append("</div>")

        html_parts.append("</body>")
        html_parts.append("</html>")

        return "\n".join(html_parts)

    def format_text(self, result: SearchResult) -> str:
        """Format result as plain text.

        Args:
            result: SearchResult to format.

        Returns:
            Plain text formatted string.
        """
        lines = []

        lines.append("=" * 80)
        lines.append("WERDEEP SEARCH RESULTS")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Query: {result.query}")
        lines.append(f"Status: {result.status}")
        lines.append(f"Pages Crawled: {result.metadata.pages_crawled}")
        lines.append(f"Depth Achieved: {result.metadata.depth_achieved}")
        lines.append(f"Duration: {result.metadata.duration_ms}ms")
        if hasattr(result.metadata, "duplicate_count") and result.metadata.duplicate_count > 0:
            lines.append(f"Duplicate URLs Skipped: {result.metadata.duplicate_count}")
        lines.append("")

        if result.status == "error":
            lines.append("ERROR:")
            lines.append(f"  Code: {result.error.code}")
            lines.append(f"  Message: {result.error.message}")
            lines.append(f"  Action: {result.error.action}")
            lines.append("")
            return "\n".join(lines)

        lines.append("RESULTS:")
        lines.append("")

        for idx, item in enumerate(result.results, 1):
            lines.append(f"Result {idx}:")
            lines.append("-" * 80)
            lines.append(f"Title: {item.title or 'Untitled'}")
            lines.append(f"URL: {item.url}")
            lines.append(f"Depth: {item.depth}")
            lines.append(f"Timestamp: {item.timestamp}")
            lines.append("")
            lines.append("Content:")
            lines.append(item.content)
            lines.append("")

            if item.code_blocks:
                lines.append("Code Blocks:")
                for cb in item.code_blocks:
                    cb_dict = cb if isinstance(cb, dict) else cb.to_dict()
                    lang = cb_dict.get("language", "unknown") or "unknown"
                    lines.append(f"  [{lang}]")
                    for code_line in cb_dict.get("content", "").splitlines():
                        lines.append(f"    {code_line}")
                lines.append("")

            if item.links:
                lines.append("Links Found:")
                for link in item.links:
                    lines.append(f"  - {link}")
                lines.append("")

            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)

    def format(self, result: SearchResult, format_type: str) -> str:
        """Format result in specified format.

        Args:
            result: SearchResult to format.
            format_type: Output format (json, markdown, html, text).

        Returns:
            Formatted string.

        Raises:
            ValueError: If format_type is invalid.
        """
        if format_type == "json":
            return self.format_json(result)
        elif format_type == "markdown":
            return self.format_markdown(result)
        elif format_type == "html":
            return self.format_html(result)
        elif format_type == "text":
            return self.format_text(result)
        else:
            raise ValueError(f"Invalid format type: {format_type}")
