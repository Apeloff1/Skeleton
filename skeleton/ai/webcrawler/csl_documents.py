"""Bounded Citation Style Language JSON bibliography extraction.

Only literal title/author/year/publisher/DOI data is retained. Unknown
fields, links, HTML, script and nested attributes are not dereferenced.
"""
from __future__ import annotations

import json
from typing import Any

from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

CSL_MEDIA_TYPES = frozenset({
    "application/vnd.citationstyles.csl+json", "application/x-csl+json",
})
_ALLOWED = ("title", "type", "publisher", "container-title", "DOI", "volume", "issue", "page")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ResearchFormatError("duplicate CSL property")
        data[key] = value
    return data


def _finite_constant(value: str):
    raise ResearchFormatError("nonfinite CSL number")


def _literal(value: Any, maxlen: int = 2048) -> str:
    if not isinstance(value, str) or len(value) > maxlen:
        return ""
    return value.strip()


def extract_csl(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        items = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=_finite_constant)
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid CSL JSON source") from exc
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not 1 <= len(items) <= 256:
        raise ResearchFormatError("invalid CSL reference capacity")
    out = []
    title = ""
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ResearchFormatError("invalid CSL reference")
        name = _literal(item.get("title"))
        if not name:
            raise ResearchFormatError("CSL title missing")
        title = title or name
        parts = [f"title: {name}"]
        for key in _ALLOWED[1:]:
            value = _literal(item.get(key))
            if value:
                parts.append(f"{key}: {value}")
        authors = item.get("author", [])
        if not isinstance(authors, list) or len(authors) > 64:
            raise ResearchFormatError("CSL author count exceeded")
        for author in authors:
            if not isinstance(author, dict):
                raise ResearchFormatError("invalid CSL author")
            family = _literal(author.get("family"), 256)
            given = _literal(author.get("given"), 256)
            if family or given:
                parts.append(f"author: {given} {family}".strip())
        issued = item.get("issued", {})
        if not isinstance(issued, dict):
            raise ResearchFormatError("invalid CSL issue date")
        values = issued.get("date-parts", [])
        if values:
            if not isinstance(values, list) or len(values) > 2:
                raise ResearchFormatError("invalid CSL date parts")
            primary = values[0]
            if (not isinstance(primary, list) or not 1 <= len(primary) <= 3
                    or any(type(x) is not int or x < 1 or x > 9999 for x in primary)):
                raise ResearchFormatError("invalid CSL date")
            parts.append("date: " + "-".join(str(x) for x in primary))
        out.append(f"Reference {i}: " + "; ".join(parts))
    return project_lines(out, title=title, max_chars=max_chars)
