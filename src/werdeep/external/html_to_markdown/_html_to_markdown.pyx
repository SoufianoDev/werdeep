from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html import unescape
from html.parser import HTMLParser
from textwrap import fill
from typing import Any, TypedDict

from werdeep.external.html_to_markdown.exceptions import EmptyHtmlError
from werdeep.external.html_to_markdown.options import ConversionOptions, PreprocessingOptions


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[Any]


class GridCell(TypedDict):
    content: str
    row: int
    col: int
    row_span: int
    col_span: int
    is_header: bool


class TableGrid(TypedDict):
    rows: int
    cols: int
    cells: list[GridCell]


class ExtractedTable(TypedDict):
    grid: TableGrid
    markdown: str


class ProcessingWarning(TypedDict):
    message: str
    kind: str


class ConversionResult(TypedDict):
    content: str | None
    document: None
    metadata: dict[str, Any] | None
    tables: list[ExtractedTable]
    images: list[Any]
    warnings: list[ProcessingWarning]


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

_BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "body",
    "div",
    "dl",
    "dt",
    "dd",
    "figure",
    "figcaption",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "thead",
    "tfoot",
    "tr",
    "ul",
}

_SKIP_WITH_PREPROCESS = {
    "script",
    "style",
}

_AD_CLASS_PATTERNS = {
    "ad",
    "ads",
    "adv",
    "advert",
    "advertisement",
    "adsense",
    "ad-placement",
    "ad-banner",
    "ad-container",
    "ad-wrapper",
    "ad-slot",
    "ad-unit",
    "sponsor",
    "sponsored",
    "sponsors",
    "sponsorship",
    "patreon",
    "buymeacoffee",
    "ko-fi",
    "affiliate",
    "promotion",
    "promo",
}

_PRESET_REMOVALS = {
    "minimal": set(),
    "standard": {"nav", "script", "style"},
    "aggressive": {"nav", "script", "style", "aside", "footer", "header", "form"},
}


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = _Node("document", {}, [])
        self.stack: list[_Node] = [self.root]

    def _append_text(self, text: str) -> None:
        if text:
            self.stack[-1].children.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {k.lower(): (v or "") for k, v in attrs}, [])
        self.stack[-1].children.append(node)
        if tag.lower() not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {k.lower(): (v or "") for k, v in attrs}, [])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for idx in range(len(self.stack) - 1, 0, -1):
            if self.stack[idx].tag == tag:
                del self.stack[idx:]
                return

    def handle_data(self, data: str) -> None:
        self._append_text(unescape(data))

    def handle_entityref(self, name: str) -> None:
        self._append_text(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self._append_text(unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        return


class _Preprocessor:
    def __init__(self, options: PreprocessingOptions) -> None:
        self.options = options
        self.removals = set(_PRESET_REMOVALS.get(options.preset, set()))
        if options.remove_navigation:
            self.removals.add("nav")
        if options.remove_forms:
            self.removals.add("form")
        self.removals.update(_SKIP_WITH_PREPROCESS)
        self.remove_ads = options.remove_ads

    def _is_ad_element(self, node: _Node) -> bool:
        if node.tag != "div":
            return False
        classes = node.attrs.get("class", "")
        if not classes:
            return False
        for cls in classes.split():
            normalized = cls.lower().replace("_", "-").replace("–", "-").replace("—", "-")
            if normalized in _AD_CLASS_PATTERNS:
                return True
            for pattern in _AD_CLASS_PATTERNS:
                if normalized.startswith(pattern) or normalized.endswith(pattern):
                    return True
        return False

    def prune(self, node: _Node) -> None:
        kept: list[Any] = []
        for child in node.children:
            if isinstance(child, _Node):
                if child.tag in self.removals:
                    continue
                if self.remove_ads and self._is_ad_element(child):
                    continue
                self.prune(child)
            kept.append(child)
        node.children = kept


@dataclass(slots=True)
class _RenderState:
    tables: list[ExtractedTable]
    images: list[dict[str, Any]]
    warnings: list[ProcessingWarning]
    metadata: dict[str, Any]


def _get_attr(node: _Node, name: str) -> str:
    return node.attrs.get(name, "")


def _normalize_text(text: str, strict: bool) -> str:
    if strict:
        return text
    return " ".join(text.split())


def _escape_markdown(text: str, options: ConversionOptions) -> str:
    if not text:
        return text
    escape_chars = set()
    if options.escape_asterisks:
        escape_chars.add("*")
    if options.escape_underscores:
        escape_chars.add("_")
    if options.escape_misc:
        escape_chars.update({"[", "]", "(", ")", "#", "+", "-", ".", "!", "|", ">"})
    if options.escape_ascii:
        escape_chars.update({chr(i) for i in range(33, 127)})
    if not escape_chars:
        return text.replace("\\", "\\\\")
    out: list[str] = []
    for ch in text:
        if ch in escape_chars:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _render_children(node: _Node, options: ConversionOptions, state: _RenderState, *, inline: bool, in_pre: bool = False) -> str:
    pieces: list[str] = []
    for child in node.children:
        pieces.append(_render(child, options, state, inline=inline, in_pre=in_pre, parent=node.tag))
    if inline:
        return "".join(pieces)
    return _join_blocks(pieces)


def _cleanup_block(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _join_blocks(parts: list[str]) -> str:
    cleaned = [part.strip("\n") for part in parts if part and part.strip()]
    return "\n\n".join(cleaned)


def _render_inline_children(node: _Node, options: ConversionOptions, state: _RenderState, *, in_pre: bool = False) -> str:
    parts: list[str] = []
    for child in node.children:
        part = _render(child, options, state, inline=True, in_pre=in_pre, parent=node.tag)
        if part:
            parts.append(part)
    return "".join(parts)


def _render_heading(node: _Node, options: ConversionOptions, state: _RenderState, level: int) -> str:
    text = _cleanup_block(_render_inline_children(node, options, state))
    if not text:
        return ""
    if options.heading_style == "underlined" and level in {1, 2}:
        underline = "=" if level == 1 else "-"
        return f"{text}\n{underline * max(len(text), 3)}"
    hashes = "#" * level
    if options.heading_style == "atx_closed":
        return f"{hashes} {text} {hashes}"
    return f"{hashes} {text}"


def _render_link(node: _Node, options: ConversionOptions, state: _RenderState) -> str:
    href = _get_attr(node, "href")
    title = _get_attr(node, "title")
    text = _render_inline_children(node, options, state)
    if not href:
        return text
    if options.autolinks and text.strip() == href and not title:
        return f"<{href}>"
    if title:
        return f'[{text}]({href} "{title}")'
    return f"[{text}]({href})"


def _render_image(node: _Node, options: ConversionOptions, state: _RenderState) -> str:
    src = _get_attr(node, "src")
    alt = _get_attr(node, "alt")
    title = _get_attr(node, "title")
    image = {"src": src, "alt": alt, "title": title}
    if options.extract_images:
        state.images.append(image)
    if options.skip_images:
        return alt
    if title:
        return f'![{alt}]({src} "{title}")'
    return f"![{alt}]({src})"


def _render_code_inline(text: str) -> str:
    if "`" not in text:
        return f"`{text}`"
    ticks = "`" * (text.count("`") + 1)
    return f"{ticks} {text} {ticks}"


def _render_pre(node: _Node, options: ConversionOptions, state: _RenderState) -> str:
    language = options.code_language
    for child in node.children:
        if isinstance(child, _Node) and child.tag == "code":
            cls = _get_attr(child, "class")
            if cls:
                for token in cls.split():
                    if token.startswith("language-"):
                        language = token.removeprefix("language-")
                        break
            text = _render_inline_children(child, options, state, in_pre=True)
            break
    else:
        text = _render_inline_children(node, options, state, in_pre=True)
    text = text.replace("\r\n", "\n").rstrip("\n")
    if options.code_block_style == "indented":
        return "\n".join(("    " + line if line else "" for line in text.splitlines()))
    fence = "```" if options.code_block_style == "backticks" else "~~~"
    first_line = f"{fence}{language}" if language else fence
    return f"{first_line}\n{text}\n{fence}"


def _render_list(node: _Node, options: ConversionOptions, state: _RenderState, *, ordered: bool) -> str:
    items: list[str] = []
    index = 1
    for child in node.children:
        if not isinstance(child, _Node) or child.tag != "li":
            continue
        items.append(_render_list_item(child, options, state, ordered=ordered, index=index))
        index += 1
    return "\n".join(items)


def _list_indent(options: ConversionOptions, level: int) -> str:
    if options.list_indent_type == "tabs":
        return "\t" * level
    return " " * (options.list_indent_width * level)


def _render_list_item(node: _Node, options: ConversionOptions, state: _RenderState, *, ordered: bool, index: int) -> str:
    nested_lists: list[str] = []
    inline_parts: list[str] = []
    block_parts: list[str] = []
    for child in node.children:
        if isinstance(child, _Node) and child.tag in {"ul", "ol"}:
            nested_lists.append(_render_list(child, options, state, ordered=(child.tag == "ol")))
            continue
        rendered = _render(child, options, state, inline=True, parent="li")
        if rendered.strip():
            inline_parts.append(rendered)
    content = _cleanup_block("".join(inline_parts))
    marker = f"{index}." if ordered else f"{options.bullets[0] if options.bullets else '-'}"
    if options.list_indent_type == "tabs":
        prefix = ""
        hang = "\t"
    else:
        prefix = ""
        hang = " " * (len(marker) + 1)
    if content:
        lines = content.splitlines()
        first = f"{marker} {lines[0]}"
        rest = [hang + line if options.list_indent_type != "tabs" else "\t" + line for line in lines[1:]]
        item = "\n".join([first, *rest]) if rest else first
    else:
        item = marker
    if nested_lists:
        nested = "\n".join(nested_lists)
        indent = _list_indent(options, 1)
        nested = "\n".join((indent + line) if line else line for line in nested.splitlines())
        item = f"{item}\n{nested}" if item else nested
    return item


def _render_blockquote(node: _Node, options: ConversionOptions, state: _RenderState) -> str:
    body = _render_children(node, options, state, inline=False)
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(f"> {line}" for line in lines)


def _render_table(node: _Node, options: ConversionOptions, state: _RenderState) -> str:
    rows: list[list[str]] = []
    grid_cells: list[GridCell] = []
    header_row = False
    row_index = 0
    for tr in node.children:
        if not isinstance(tr, _Node) or tr.tag not in {"tr", "thead", "tbody", "tfoot"}:
            continue
        tr_rows = tr.children if tr.tag == "tr" else [c for c in tr.children if isinstance(c, _Node) and c.tag == "tr"]
        for row in tr_rows:
            if not isinstance(row, _Node) or row.tag != "tr":
                continue
            cells: list[str] = []
            col_index = 0
            row_is_header = False
            for cell in row.children:
                if not isinstance(cell, _Node) or cell.tag not in {"th", "td"}:
                    continue
                cell_text = _cleanup_block(_render_inline_children(cell, options, state))
                cells.append(cell_text)
                is_header = cell.tag == "th" or row_is_header
                row_is_header = row_is_header or cell.tag == "th"
                grid_cells.append(
                    {
                        "content": cell_text,
                        "row": row_index,
                        "col": col_index,
                        "row_span": 1,
                        "col_span": 1,
                        "is_header": is_header,
                    }
                )
                col_index += 1
            if cells:
                rows.append(cells)
                header_row = header_row or row_is_header
                row_index += 1
    if not rows:
        return ""
    cols = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (cols - len(row)) for row in rows]
    header = normalized_rows[0]
    body = normalized_rows[1:]
    align = ["---"] * cols
    table_lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(align) + " |"]
    for row in body:
        table_lines.append("| " + " | ".join(row) + " |")
    state.tables.append(
        {
            "grid": {"rows": len(rows), "cols": cols, "cells": grid_cells},
            "markdown": "\n".join(table_lines),
        }
    )
    return state.tables[-1]["markdown"]


def _render_text(text: str, options: ConversionOptions, *, in_pre: bool) -> str:
    if in_pre:
        return text
    return _escape_markdown(_normalize_text(text, options.whitespace_mode == "strict"), options)


def _render(node: str | _Node, options: ConversionOptions, state: _RenderState, *, inline: bool, in_pre: bool = False, parent: str | None = None) -> str:
    if isinstance(node, str):
        return _render_text(node, options, in_pre=in_pre)

    tag = node.tag
    if tag in _SKIP_WITH_PREPROCESS:
        return ""
    if tag in {"document", "html", "body"}:
        parts = [_render(child, options, state, inline=False, in_pre=in_pre, parent=tag) for child in node.children]
        return _join_blocks(parts) if not inline else "".join(parts)
    if tag == "p":
        content = _render_inline_children(node, options, state)
        return content
    if tag in {"div", "section", "article", "main", "header", "footer", "aside", "nav", "figure", "figcaption"}:
        content = _render_children(node, options, state, inline=False, in_pre=in_pre)
        return content
    if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
        return _render_heading(node, options, state, int(tag[1]))
    if tag in {"strong", "b"}:
        symbol = options.strong_em_symbol or "*"
        text = _render_inline_children(node, options, state, in_pre=in_pre)
        return f"{symbol * 2}{text}{symbol * 2}"
    if tag in {"em", "i"}:
        symbol = options.strong_em_symbol or "*"
        text = _render_inline_children(node, options, state, in_pre=in_pre)
        return f"{symbol}{text}{symbol}"
    if tag == "code":
        text = _render_inline_children(node, options, state, in_pre=True)
        if parent == "pre":
            return text
        return _render_code_inline(text)
    if tag == "pre":
        return _render_pre(node, options, state)
    if tag == "br":
        return "\\\n" if options.newline_style == "backslash" else "  \n"
    if tag == "hr":
        return "---"
    if tag == "a":
        return _render_link(node, options, state)
    if tag == "img":
        return _render_image(node, options, state)
    if tag == "blockquote":
        return _render_blockquote(node, options, state)
    if tag == "ul":
        return _render_list(node, options, state, ordered=False)
    if tag == "ol":
        return _render_list(node, options, state, ordered=True)
    if tag == "table":
        return _render_table(node, options, state)
    if tag in {"thead", "tbody", "tfoot", "tr", "th", "td"}:
        return _render_children(node, options, state, inline=inline, in_pre=in_pre)
    if tag in {"script", "style"}:
        return ""
    if tag == "meta":
        return ""
    if tag == "title":
        title = _cleanup_block(_render_inline_children(node, options, state))
        if title and "title" not in state.metadata:
            state.metadata["title"] = title
        return title
    if tag == "mark":
        text = _render_inline_children(node, options, state, in_pre=in_pre)
        if options.highlight_style == "html":
            return f"<mark>{text}</mark>"
        if options.highlight_style == "bold":
            return f"**{text}**"
        return f"=={text}=="
    if tag == "sub":
        text = _render_inline_children(node, options, state, in_pre=in_pre)
        return f"{options.sub_symbol or '<sub>'}{text}{options.sub_symbol or '</sub>'}" if options.sub_symbol else f"<sub>{text}</sub>"
    if tag == "sup":
        text = _render_inline_children(node, options, state, in_pre=in_pre)
        return f"{options.sup_symbol or '<sup>'}{text}{options.sup_symbol or '</sup>'}" if options.sup_symbol else f"<sup>{text}</sup>"
    if tag == "span":
        return _render_inline_children(node, options, state, in_pre=in_pre)
    if tag in {"li"}:
        return _render_children(node, options, state, inline=inline, in_pre=in_pre)
    if tag == "head":
        _render_children(node, options, state, inline=False, in_pre=in_pre)
        return ""
    if tag in {"form"}:
        return _render_children(node, options, state, inline=False, in_pre=in_pre)
    if tag in {"dl", "dt", "dd"}:
        return _render_children(node, options, state, inline=inline, in_pre=in_pre)
    if tag == "noscript":
        return _render_inline_children(node, options, state, in_pre=in_pre)
    if tag == "video" or tag == "audio":
        return _render_inline_children(node, options, state, in_pre=in_pre)
    if tag == "details":
        return _render_children(node, options, state, inline=False, in_pre=in_pre)
    if tag == "summary":
        return _render_inline_children(node, options, state, in_pre=in_pre)
    if tag == "html" or tag == "body":
        return _render_children(node, options, state, inline=inline, in_pre=in_pre)
    return _render_children(node, options, state, inline=inline, in_pre=in_pre)


def _apply_wrap(text: str, width: int) -> str:
    if width <= 0:
        return text
    output: list[str] = []
    paragraph: list[str] = []
    in_code = False
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if paragraph:
                output.append(fill(" ".join(paragraph), width=width))
                paragraph.clear()
            output.append(line)
            in_code = not in_code
            continue
        if in_code or stripped.startswith("|") or stripped.startswith(">") or stripped.startswith("    "):
            if paragraph:
                output.append(fill(" ".join(paragraph), width=width))
                paragraph.clear()
            output.append(line)
            continue
        if not stripped:
            if paragraph:
                output.append(fill(" ".join(paragraph), width=width))
                paragraph.clear()
            output.append("")
            continue
        paragraph.append(stripped)
    if paragraph:
        output.append(fill(" ".join(paragraph), width=width))
    return "\n".join(output)


def _extract_metadata(root: _Node) -> dict[str, Any] | None:
    meta: dict[str, Any] = {}
    for child in root.children:
        if isinstance(child, _Node) and child.tag == "html":
            for head_child in child.children:
                if isinstance(head_child, _Node) and head_child.tag == "head":
                    for item in head_child.children:
                        if isinstance(item, _Node) and item.tag == "meta":
                            name = item.attrs.get("name") or item.attrs.get("property")
                            content = item.attrs.get("content", "")
                            if name and content:
                                meta[name] = content
                        if isinstance(item, _Node) and item.tag == "title":
                            title = _cleanup_block(_render_inline_children(item, ConversionOptions(), _RenderState([], [], [], {})))
                            if title:
                                meta.setdefault("title", title)
    return meta or None


def convert(
    html: str,
    options: ConversionOptions | None = None,
    preprocessing: PreprocessingOptions | None = None,
    visitor: object | None = None,
) -> ConversionResult:
    if not html:
        raise EmptyHtmlError()

    options = options or ConversionOptions()
    if preprocessing is None:
        preprocessing = options.preprocessing if options.preprocessing is not None else PreprocessingOptions(enabled=False)

    parser = _TreeBuilder()
    parser.feed(html)
    parser.close()
    root = parser.root

    if preprocessing.enabled:
        _Preprocessor(preprocessing).prune(root)

    state = _RenderState(tables=[], images=[], warnings=[], metadata={})
    content = _render(root, options, state, inline=False)
    content = _cleanup_block(content)
    if options.extract_metadata:
        state.metadata.update(_extract_metadata(root) or {})
    else:
        state.metadata = {}

    if options.strip_newlines:
        content = content.replace("\n", " ")
    if options.wrap:
        content = _apply_wrap(content, options.wrap_width)

    if options.output_format == "plain":
        content = _render_plain_text(root, options)

    return {
        "content": content,
        "document": None,
        "metadata": state.metadata or None,
        "tables": state.tables,
        "images": state.images,
        "warnings": state.warnings,
    }


def _render_plain_text(root: _Node, options: ConversionOptions) -> str:
    parts: list[str] = []
    for child in root.children:
        parts.append(_plain_render(child, options))
    text = _cleanup_block("\n\n".join(part for part in parts if part))
    if options.wrap:
        return _apply_wrap(text, options.wrap_width)
    return text


def _plain_render(node: str | _Node, options: ConversionOptions) -> str:
    if isinstance(node, str):
        return _normalize_text(node, options.whitespace_mode == "strict")
    if node.tag in {"script", "style"}:
        return ""
    if node.tag == "br":
        return "\n"
    if node.tag in {"p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "blockquote", "li", "tr"}:
        return _cleanup_block("".join(_plain_render(child, options) for child in node.children))
    if node.tag == "table":
        return _cleanup_block("\n".join(_plain_render(child, options) for child in node.children))
    if node.tag in {"ul", "ol"}:
        return _cleanup_block("\n".join(_plain_render(child, options) for child in node.children))
    if node.tag == "img":
        return node.attrs.get("alt", "")
    return "".join(_plain_render(child, options) for child in node.children)


__all__ = [
    "ConversionOptions",
    "ConversionResult",
    "ExtractedTable",
    "GridCell",
    "PreprocessingOptions",
    "ProcessingWarning",
    "TableGrid",
    "convert",
]
