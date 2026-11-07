"""Inert HTML table and JSON-LD projection for canonical Dragon research capture.

The ordinary HTML extractor still owns hyperlinks; this module enriches only
the retained unreviewed text with labeled table cells and embedded JSON-LD.
No scripts, CSS, web components, microdata URLs, images or iframe content
are executed, fetched, evaluated or turned into crawler permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from .document_formats import DocumentFormatError, extract_json


MAX_TABLES = 16
MAX_ROWS = 256
MAX_COLUMNS = 32
MAX_CELL_CHARS = 2048
MAX_JSONLD_BLOCKS = 8
MAX_JSONLD_BYTES = 131072
MAX_HTML_TAGS = 16384


class HTMLSemanticError(ValueError):
    """HTML semantic annotation exceeded a finite, parse-only budget."""


@dataclass(frozen=True)
class HTMLSemantics:
    text: str
    tables: int
    table_rows: int
    jsonld_blocks: int
    malformed_jsonld: int
    truncated: bool
    links: tuple[str, ...] = ()
    body_executed: bool = False
    reference_trusted: bool = False


class _SemanticReader(HTMLParser):
    def __init__(self, max_chars: int):
        super().__init__(convert_charrefs=True)
        self.max_chars = max_chars
        self.tags = 0
        self.table_depth = 0
        self.tables = 0
        self.rows = 0
        self.lines: list[str] = []
        self.projection_chars = 0
        self.truncated = False
        self.row: list[tuple[str, str]] | None = None
        self.cell_name: str | None = None
        self.cell_content: list[str] = []
        self.headers: list[str] = []
        self.header_candidate: list[tuple[str, str]] = []
        self.script_jsonld = False
        self.script_content: list[str] = []
        self.script_bytes = 0
        self.jsonld_blocks = 0
        self.malformed_jsonld = 0

    def _push(self, line: str) -> None:
        length = len(line) + 1
        if self.projection_chars + length > self.max_chars:
            self.truncated = True
            return
        self.lines.append(line)
        self.projection_chars += length

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > MAX_HTML_TAGS:
            raise HTMLSemanticError("HTML exceeds semantic tag capacity")
        tag = tag.lower()
        if tag == "script":
            attr = dict(attrs)
            mime = (attr.get("type") or "").lower().split(";", 1)[0].strip()
            self.script_jsonld = mime == "application/ld+json"
            self.script_content = []
            self.script_bytes = 0
        if tag == "table":
            if self.table_depth == 0:
                self.tables += 1
                if self.tables > MAX_TABLES:
                    raise HTMLSemanticError("too many source HTML tables")
                self.headers = []
            self.table_depth += 1
        elif self.table_depth == 1 and tag == "tr":
            self.row = []
        elif self.table_depth == 1 and tag in ("th", "td") and self.row is not None:
            self.cell_name = tag
            self.cell_content = []

    def handle_data(self, data):
        if self.script_jsonld:
            self.script_bytes += len(data.encode("utf-8"))
            if self.script_bytes > MAX_JSONLD_BYTES:
                raise HTMLSemanticError("embedded JSON-LD exceeds finite byte cap")
            self.script_content.append(data)
        if self.table_depth == 1 and self.cell_name:
            used = sum(len(chunk) for chunk in self.cell_content)
            if used + len(data) > MAX_CELL_CHARS:
                raise HTMLSemanticError("HTML table cell exceeds text limit")
            self.cell_content.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script":
            if self.script_jsonld:
                self.jsonld_blocks += 1
                if self.jsonld_blocks > MAX_JSONLD_BLOCKS:
                    raise HTMLSemanticError("too many JSON-LD source blocks")
                raw = "".join(self.script_content).strip()
                if raw:
                    try:
                        parsed = extract_json(
                            raw, max_chars=min(self.max_chars, 12000), max_links=0,
                        )
                    except DocumentFormatError:
                        self.malformed_jsonld += 1
                    else:
                        self._push(f"Embedded JSON-LD {self.jsonld_blocks}:")
                        for line in parsed.text.splitlines():
                            self._push("  " + line)
                        self.truncated |= parsed.truncated
            self.script_jsonld = False
            self.script_content = []
            self.script_bytes = 0
        if self.table_depth == 1 and tag in ("th", "td") and self.cell_name == tag:
            value = " ".join("".join(self.cell_content).split())
            if self.row is not None:
                if len(self.row) >= MAX_COLUMNS:
                    raise HTMLSemanticError("too many table columns")
                self.row.append((tag, value))
            self.cell_name = None
            self.cell_content = []
        elif self.table_depth == 1 and tag == "tr" and self.row is not None:
            if not self.headers and self.row and all(k == "th" for k, _ in self.row):
                self.headers = [
                    value[:128] or f"column_{i + 1}"
                    for i, (_, value) in enumerate(self.row)
                ]
            elif self.row:
                self.rows += 1
                if self.rows > MAX_ROWS:
                    raise HTMLSemanticError("HTML table row budget exceeded")
                cells = []
                for i, (_, value) in enumerate(self.row):
                    label = self.headers[i] if i < len(self.headers) else f"column_{i + 1}"
                    cells.append(f"{label}: {value}")
                self._push(f"Table {self.tables} row {self.rows}: " + "; ".join(cells))
            self.row = None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1
            if self.table_depth == 0:
                self.row = None
                self.cell_name = None
                self.cell_content = []


def extract_html_semantics(
    raw: str, *, max_chars: int = 8000,
) -> HTMLSemantics:
    if (
        not isinstance(raw, str) or len(raw) > 2_500_000
        or type(max_chars) is not int or not 128 <= max_chars <= 2_097_152
    ):
        raise HTMLSemanticError("invalid HTML semantic text capacity")
    parser = _SemanticReader(max_chars)
    try:
        parser.feed(raw)
        parser.close()
    except (ValueError, RecursionError) as exc:
        raise HTMLSemanticError("malformed or overlarge HTML semantics") from exc
    return HTMLSemantics(
        text="\n".join(parser.lines),
        tables=parser.tables,
        table_rows=parser.rows,
        jsonld_blocks=parser.jsonld_blocks,
        malformed_jsonld=parser.malformed_jsonld,
        truncated=parser.truncated,
    )
