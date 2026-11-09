"""Privacy-minimizing HAR network timeline evidence without request replay.

HAR carries cookies, credentials, post bodies and arbitrary IPs; these are
not retained. Only finite method, response status, elapsed time, content
type, size and neutral time labels are represented. No URL is exported.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

HAR_MEDIA_TYPES = frozenset({"application/har+json", "application/x-har+json"})


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ResearchFormatError("duplicate HAR JSON key")
        obj[key] = value
    return obj


def _constant(value: str) -> Any:
    raise ResearchFormatError("nonfinite HAR numeric constant")


def _number(value: object, *, lower: int = 0, upper: int = 2_097_152) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not lower <= value <= upper):
        raise ResearchFormatError("invalid HAR measurement")
    return float(value)


def extract_har(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        data = json.loads(
            raw, object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid HAR JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("log"), dict):
        raise ResearchFormatError("HAR log envelope missing")
    log = data["log"]
    entries = log.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 256:
        raise ResearchFormatError("HAR entry capacity invalid")
    lines = []
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ResearchFormatError("invalid HAR entry")
        req, resp = entry.get("request"), entry.get("response")
        if not isinstance(req, dict) or not isinstance(resp, dict):
            raise ResearchFormatError("HAR request/response envelope missing")
        method = req.get("method")
        if not isinstance(method, str) or method not in (
            "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS",
        ):
            raise ResearchFormatError("invalid HAR method")
        status = resp.get("status")
        if type(status) is not int or not 0 <= status <= 599:
            raise ResearchFormatError("invalid HAR status")
        elapsed = _number(entry.get("time"), upper=1_800_000)
        content = resp.get("content", {})
        if not isinstance(content, dict):
            raise ResearchFormatError("invalid HAR content summary")
        size = _number(content.get("size", 0))
        mime = content.get("mimeType", "")
        if not isinstance(mime, str) or len(mime) > 256:
            raise ResearchFormatError("invalid HAR MIME label")
        # Text and headers from HAR are never retained. Only the leading
        # syntax of an explicit MIME type is exposed, without parameters.
        ctype = mime.split(";", 1)[0].lower().strip()
        if not ctype or not all(x.isascii() and (x.isalnum() or x in ".+-/") for x in ctype):
            ctype = "unspecified"
        lines.append(
            f"HTTP trace {i}: method: {method}; status: {status}; "
            f"elapsed_ms: {elapsed:.3f}; body_bytes: {int(size)}; "
            f"content_type: {ctype[:128]}"
        )
    return project_lines(lines, title="HAR network performance trace", max_chars=max_chars)
