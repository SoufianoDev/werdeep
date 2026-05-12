r"""html-to-markdown: Convert HTML to Markdown with a Python API and a Cython core.

API:
    from html_to_markdown import convert, ConversionOptions

    result = convert("<h1>Hello</h1>")
    print(result["content"])  # "# Hello\n"
"""

from werdeep.external.html_to_markdown.api import ConversionResult, convert
from werdeep.external.html_to_markdown.exceptions import (
    ConflictingOptionsError,
    EmptyHtmlError,
    HtmlToMarkdownError,
    InvalidParserError,
    MissingDependencyError,
)
from werdeep.external.html_to_markdown.options import (
    ConversionOptions,
    OutputFormat,
    PreprocessingOptions,
)

__all__ = [
    "ConflictingOptionsError",
    "ConversionOptions",
    "ConversionResult",
    "EmptyHtmlError",
    "HtmlToMarkdownError",
    "InvalidParserError",
    "MissingDependencyError",
    "OutputFormat",
    "PreprocessingOptions",
    "convert",
]

__version__ = "3.1.0"
