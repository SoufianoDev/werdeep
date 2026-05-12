"""High-level Python API backed by the Cython core."""

from __future__ import annotations

from typing import Any, TypedDict, cast

import werdeep.external.html_to_markdown._html_to_markdown as _core
from werdeep.external.html_to_markdown.options import ConversionOptions, PreprocessingOptions


class GridCell(TypedDict):
    """A single cell in a structured table grid."""

    content: str
    row: int
    col: int
    row_span: int
    col_span: int
    is_header: bool


class TableGrid(TypedDict):
    """Structured table grid with cell-level data."""

    rows: int
    cols: int
    cells: list[GridCell]


class ExtractedTable(TypedDict):
    """A table extracted via the ConversionResult API."""

    grid: TableGrid
    markdown: str


class ProcessingWarning(TypedDict):
    """A non-fatal warning emitted during conversion."""

    message: str
    kind: str


class ConversionResult(TypedDict):
    """Full result of the convert() API."""

    content: str | None
    document: None
    metadata: dict[str, Any] | None
    tables: list[ExtractedTable]
    images: list[Any]
    warnings: list[ProcessingWarning]


def convert(
    html: str,
    options: ConversionOptions | None = None,
    preprocessing: PreprocessingOptions | None = None,
    visitor: object | None = None,
) -> ConversionResult:
    """Convert HTML to Markdown.

    Returns a typed dict containing the converted content alongside all extracted
    metadata, tables, images, and processing warnings in a single pass.

    Args:
        html: HTML string to convert
        options: Optional conversion configuration
        preprocessing: Optional preprocessing configuration
        visitor: Optional visitor object with callback methods for custom element handling

    Returns:
        ConversionResult dict with keys:
            - content (str | None): Converted markdown, or None in extraction-only mode
            - document (None): Document structure (not yet exposed in bindings)
            - metadata (dict | None): Extracted HTML metadata (when metadata feature is enabled)
            - tables (list[dict]): Extracted tables with grid and markdown fields
            - images (list): Extracted inline images (when inline-images feature is enabled)
            - warnings (list[dict]): Non-fatal processing warnings
    """
    return cast("ConversionResult", _core.convert(html, options, preprocessing=preprocessing, visitor=visitor))


__all__ = [
    "ConversionResult",
    "ExtractedTable",
    "GridCell",
    "ProcessingWarning",
    "TableGrid",
    "convert",
]
