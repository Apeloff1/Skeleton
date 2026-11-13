"""Conservative N-Triples and N-Quads text evidence projection.

RDF IRIs are quoted source facts only, never crawler frontier proposals.
This intentionally does not resolve contexts, follow IRIs or expand RDF
predicates into executable actions. Invalid/unsupported serialization fails.
"""
from __future__ import annotations

import re

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

RDF_MEDIA_TYPES = frozenset({"application/n-triples", "application/n-quads"})
_IRI = r"<[^<>{}\"\\\x00-\x20]{1,4096}>"
_NODE = rf"(?:{_IRI}|_:[A-Za-z][A-Za-z0-9._-]{{0,127}})"
_LITERAL = r'"(?:\\.|[^"\\]){0,8192}"(?:@[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*|\^\^' + _IRI + r")?"
_PATTERN_TRIPLE = re.compile(rf"^({_NODE})\s+({_IRI})\s+({_NODE}|{_LITERAL})\s*\.\s*$")
_PATTERN_QUAD = re.compile(rf"^({_NODE})\s+({_IRI})\s+({_NODE}|{_LITERAL})\s+({_NODE})\s*\.\s*$")


def extract_rdf_lines(
    raw: str, media_type: str, *, max_chars: int = 524288,
    max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    if media_type not in RDF_MEDIA_TYPES:
        raise ResearchFormatError("unsupported RDF text syntax")
    out = []
    pattern = _PATTERN_QUAD if media_type == "application/n-quads" else _PATTERN_TRIPLE
    for line in raw.lstrip("\ufeff").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(stripped) > 16384 or pattern.fullmatch(stripped) is None:
            raise ResearchFormatError("malformed or excessive RDF statement")
        out.append(f"RDF assertion {len(out) + 1}: {stripped}")
        if len(out) > 512:
            raise ResearchFormatError("RDF assertion capacity exceeded")
    return project_lines(out, title="RDF statements", max_chars=max_chars)
