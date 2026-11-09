"""Safe bounded OpenAPI v3 path/operation catalog, without remote references.

OpenAPI documents are untrusted API descriptions, never authorization to
contact endpoints, retrieve $ref targets, execute methods, or use source-provided
API keys. All server URLs, security schemes, headers and examples are omitted.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .openapi_graph import inspect_openapi_graph, summarize_openapi_graph
from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

OPENAPI_MEDIA_TYPES = frozenset({
    "application/openapi+json", "application/vnd.oai.openapi+json",
})
_HTTP = ("get", "head", "post", "put", "patch", "delete", "options", "trace")
_SAFE_PATH = re.compile(r"^/[A-Za-z0-9_/{}\-.~]{0,255}$")
_SAFE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ResearchFormatError("duplicate OpenAPI JSON property")
        data[key] = value
    return data


def _nonfinite(value: str) -> Any:
    raise ResearchFormatError("nonfinite OpenAPI numeric literal")


def extract_openapi(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        source = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid OpenAPI JSON") from exc
    if not isinstance(source, dict):
        raise ResearchFormatError("OpenAPI root object missing")
    version = source.get("openapi")
    if not isinstance(version, str) or not version.startswith("3.") or len(version) > 16:
        raise ResearchFormatError("only OpenAPI v3 is supported")
    paths = source.get("paths")
    if not isinstance(paths, dict) or not 1 <= len(paths) <= 256:
        raise ResearchFormatError("OpenAPI path count exceeds bounds")
    info = source.get("info", {})
    if not isinstance(info, dict):
        raise ResearchFormatError("OpenAPI info object invalid")
    title = info.get("title") or "OpenAPI contract"
    if not isinstance(title, str) or len(title) > 512:
        raise ResearchFormatError("OpenAPI title invalid")
    lines = []
    operations = 0
    for path, path_item in sorted(paths.items()):
        if (not isinstance(path, str) or not _SAFE_PATH.fullmatch(path)
                or ".." in path or "//" in path):
            raise ResearchFormatError("unsafe OpenAPI path description")
        if not isinstance(path_item, dict):
            raise ResearchFormatError("invalid OpenAPI path item")
        if "$ref" in path_item:
            # Source references do not grant remote or local authority.
            continue
        for method in _HTTP:
            if method not in path_item:
                continue
            op = path_item[method]
            if not isinstance(op, dict):
                raise ResearchFormatError("invalid OpenAPI operation")
            if "$ref" in op:
                continue
            operations += 1
            if operations > 512:
                raise ResearchFormatError("OpenAPI operation count exceeded")
            summary = op.get("summary") or op.get("description") or ""
            if not isinstance(summary, str) or len(summary) > 4096:
                raise ResearchFormatError("invalid OpenAPI operation description")
            identifier = op.get("operationId", "")
            if identifier and (
                not isinstance(identifier, str)
                or _SAFE_ID.fullmatch(identifier) is None
            ):
                identifier = "[untrusted identifier omitted]"
            responses = op.get("responses", {})
            if not isinstance(responses, dict) or len(responses) > 64:
                raise ResearchFormatError("OpenAPI response map invalid")
            codes = [
                key for key in responses
                if isinstance(key, str) and re.fullmatch(r"(?:[1-5]\d\d|default)", key)
            ]
            row = (f"API {operations}: {method.upper()} {path}; "
                   f"operation: {identifier}; summary: {summary[:512]}; "
                   f"response codes: {','.join(sorted(codes))}")
            lines.append(row)
    graph=inspect_openapi_graph(source)
    lines.extend(summarize_openapi_graph(graph))
    return project_lines(lines, title=title, max_chars=max_chars)
