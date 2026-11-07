"""Bounded root-level JSON Schema field catalog for inert source evidence.

JSON schema combinators, remote $refs, custom executable formats, examples,
web endpoints and schema directives are not interpreted or dereferenced.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

JSONSCHEMA_MEDIA_TYPES = frozenset({
    "application/schema+json", "application/vnd.schema+json",
})
_ALLOWED = frozenset({
    "string", "number", "integer", "boolean", "null", "object", "array",
})
_NAME = re.compile(r"^[A-Za-z0-9_\-.]{1,128}$")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, val in pairs:
        if key in out:
            raise ResearchFormatError("duplicate JSON Schema key")
        out[key] = val
    return out


def _reject(value: str) -> Any:
    raise ResearchFormatError("nonfinite JSON Schema number")


def extract_jsonschema(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        source = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject)
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid JSON Schema object") from exc
    if not isinstance(source, dict):
        raise ResearchFormatError("JSON Schema root must be object")
    props = source.get("properties")
    if not isinstance(props, dict) or not 1 <= len(props) <= 256:
        raise ResearchFormatError("JSON Schema property capacity invalid")
    required = source.get("required", [])
    if (not isinstance(required, list) or len(required) > 256
            or any(not isinstance(x, str) for x in required)):
        raise ResearchFormatError("invalid schema required fields")
    require = set(required)
    lines = []
    for key in sorted(props):
        if not isinstance(key, str) or not _NAME.fullmatch(key):
            raise ResearchFormatError("invalid schema property name")
        val = props[key]
        if not isinstance(val, dict):
            raise ResearchFormatError("schema property must be object")
        typ = val.get("type")
        if isinstance(typ, list):
            if not typ or len(typ) > 7 or any(type(x) is not str or x not in _ALLOWED for x in typ):
                raise ResearchFormatError("invalid property type alternatives")
            typ = "|".join(sorted(set(typ)))
        if not isinstance(typ, str) or (
            typ not in _ALLOWED and not (
                "|" in typ and set(typ.split("|")) <= _ALLOWED
            )
        ):
            typ = "unspecified"
        desc = val.get("description", "")
        if not isinstance(desc, str) or len(desc) > 2048:
            raise ResearchFormatError("invalid schema property description")
        # Values/defaults, examples, secrets, patterns and $ref are omitted.
        lines.append(
            f"Schema field {key}: type: {typ}; required: {key in require}; "
            f"description: {desc[:256]}"
        )
    title = source.get("title") or "JSON Schema fields"
    if not isinstance(title, str) or len(title) > 512:
        raise ResearchFormatError("JSON Schema title invalid")
    return project_lines(lines, title=title, max_chars=max_chars)
