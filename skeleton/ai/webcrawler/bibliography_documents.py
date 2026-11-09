"""Finite RIS and literal BibTeX capture as unreviewed bibliographic evidence.

External URLs, DOI links, BibTeX macros and citations never grant network or
knowledge authority. No TeX, shell command, code, macro or bibliography style
is expanded or executed. Unsupported symbolic concatenations fail closed.
"""
from __future__ import annotations

import re

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

BIBLIOGRAPHY_MEDIA_TYPES = frozenset({
    "application/x-research-info-systems", "text/ris",
    "application/x-bibtex", "text/x-bibtex",
})
_RIS_LINE = re.compile(r"^([A-Z][A-Z0-9])  - ?(.*)$")
_KEY = re.compile(r"^[A-Za-z0-9_.:/+-]{1,256}$")
_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_RIS_ALLOWED = frozenset({
    "TI", "T1", "AU", "A1", "PY", "Y1", "JO", "JF", "JA",
    "AB", "N2", "KW", "DO", "VL", "IS", "SP", "EP", "PB", "SN",
})
_BIB_FIELDS = frozenset({
    "title", "author", "year", "date", "journal", "booktitle",
    "abstract", "keywords", "doi", "volume", "number", "pages",
    "publisher", "isbn", "issn",
})


def _limit_value(value: str) -> str:
    if len(value) > 8192:
        raise ResearchFormatError("bibliographic field length exceeded")
    return value.strip()


def extract_ris(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] | None = None
    last_key: str | None = None
    fields = 0
    if len(raw.splitlines()) > 8192:
        raise ResearchFormatError("RIS line count exceeded")
    for line in raw.lstrip("\ufeff").splitlines():
        if not line.strip():
            continue
        match = _RIS_LINE.fullmatch(line)
        if match is None:
            if line[:1].isspace() and current is not None and last_key in _RIS_ALLOWED:
                current[last_key][-1] = _limit_value(
                    current[last_key][-1] + " " + line.strip(),
                )
                continue
            raise ResearchFormatError("invalid RIS field or continuation")
        key, value = match.groups()
        if key == "TY":
            if current is not None or len(records) >= 256:
                raise ResearchFormatError("nested or excessive RIS records")
            current, last_key = {"TY": [_limit_value(value)]}, key
            continue
        if key == "ER":
            if current is None:
                raise ResearchFormatError("RIS terminator without record")
            if current.get("TI") or current.get("T1"):
                records.append(current)
            current, last_key = None, None
            continue
        if current is None:
            raise ResearchFormatError("RIS field outside a record")
        fields += 1
        if fields > 4096:
            raise ResearchFormatError("RIS field count exceeded")
        if key in _RIS_ALLOWED:
            current.setdefault(key, []).append(_limit_value(value))
        last_key = key
    if current is not None or not records:
        raise ResearchFormatError("incomplete or empty RIS citation source")
    lines = []
    for i, row in enumerate(records, 1):
        parts = []
        for tag, label in (
            ("TI", "title"), ("T1", "alternative title"), ("AU", "author"),
            ("A1", "author"), ("PY", "year"), ("Y1", "date"), ("JO", "journal"),
            ("JF", "journal"), ("JA", "journal"), ("AB", "abstract"),
            ("N2", "abstract"), ("KW", "keyword"), ("DO", "doi"),
            ("VL", "volume"), ("IS", "issue"), ("SP", "start page"),
            ("EP", "end page"), ("PB", "publisher"), ("SN", "identifier"),
        ):
            for value in row.get(tag, ()):
                if value:
                    parts.append(f"{label}: {value}")
        lines.append(f"Reference {i}: " + "; ".join(parts))
    title = (records[0].get("TI") or records[0].get("T1") or ["Bibliography"])[0]
    return project_lines(lines, title=title, max_chars=max_chars)


def _split_fields(body: str) -> list[str]:
    """Split a BibTeX record only on commas outside quoted/braced values."""
    depth = 0
    quote = False
    escaped = False
    start = 0
    fields = []
    for i, ch in enumerate(body):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"' and depth == 0:
            quote = not quote
        elif not quote:
            if ch == "{":
                depth += 1
                if depth > 24:
                    raise ResearchFormatError("BibTeX group nesting exceeded")
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    raise ResearchFormatError("BibTeX unbalanced group")
            elif ch == "," and depth == 0:
                fields.append(body[start:i].strip())
                start = i + 1
                if len(fields) > 64:
                    raise ResearchFormatError("BibTeX field count exceeded")
    if depth or quote or escaped:
        raise ResearchFormatError("BibTeX unbalanced field values")
    fields.append(body[start:].strip())
    return [field for field in fields if field]


def _entry_body(raw: str, cursor: int) -> tuple[str, int]:
    # The caller has consumed @type{ or @type(.
    opening = raw[cursor - 1]
    closing = "}" if opening == "{" else ")"
    braces = 0
    quoted = False
    escaped = False
    start = cursor
    for idx in range(cursor, len(raw)):
        ch = raw[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"' and braces == 0:
            quoted = not quoted
        elif not quoted:
            if ch == "{":
                braces += 1
                if braces > 24:
                    raise ResearchFormatError("BibTeX group nesting exceeded")
            elif ch == "}":
                if braces:
                    braces -= 1
                elif closing == "}":
                    return raw[start:idx], idx + 1
                else:
                    raise ResearchFormatError("stray BibTeX brace")
            elif ch == ")" and closing == ")" and braces == 0:
                return raw[start:idx], idx + 1
    raise ResearchFormatError("unclosed BibTeX entry")


def extract_bibtex(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    pos, entries, lines = 0, 0, []
    first_title = ""
    while pos < len(raw):
        # Comments are not evaluated, and stray text cannot be reinterpreted
        # as trusted parser directives or source references.
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos == len(raw):
            break
        head = re.match(r"@([A-Za-z]{2,32})\s*([({])", raw[pos:])
        if head is None:
            raise ResearchFormatError("invalid or executable BibTeX entry syntax")
        kind = head.group(1).lower()
        if kind in {"string", "preamble", "comment"}:
            raise ResearchFormatError("BibTeX macro and preamble declarations denied")
        inner, pos = _entry_body(raw, pos + head.end())
        chunks = _split_fields(inner)
        if not chunks or not _KEY.fullmatch(chunks[0]):
            raise ResearchFormatError("invalid BibTeX reference identity")
        fields = {}
        for item in chunks[1:]:
            if "=" not in item:
                raise ResearchFormatError("BibTeX field assignment missing")
            key, literal = item.split("=", 1)
            key = key.strip().lower()
            literal = literal.strip()
            if not _FIELD.fullmatch(key) or key in fields:
                raise ResearchFormatError("invalid or repeated BibTeX field")
            if (len(literal) < 2
                    or not ((literal[0] == "{" and literal[-1] == "}")
                            or (literal[0] == '"' and literal[-1] == '"'))):
                raise ResearchFormatError("BibTeX symbolic macros are not expanded")
            fields[key] = _limit_value(literal[1:-1])
        if not fields.get("title"):
            raise ResearchFormatError("BibTeX record lacks a literal title")
        entries += 1
        if entries > 256:
            raise ResearchFormatError("bibliography capacity exceeded")
        title = fields["title"]
        first_title = first_title or title
        parts = [f"title: {title}"]
        for key in sorted(_BIB_FIELDS - {"title"}):
            if fields.get(key):
                parts.append(f"{key}: {fields[key]}")
        lines.append(f"Reference {entries} [{kind}, {chunks[0]}]: " + "; ".join(parts))
    if not entries:
        raise ResearchFormatError("no finite BibTeX bibliography entries")
    return project_lines(lines, title=first_title, max_chars=max_chars)
