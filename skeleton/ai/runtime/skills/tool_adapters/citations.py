"""Citation packing — quote only bytes that a tool result actually stored."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from skeleton.memory.prefix_renderer import estimate_tokens


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    source_ref: str
    excerpt: str
    tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "citation_id": self.citation_id,
            "source_ref": self.source_ref,
            "excerpt": self.excerpt,
            "tokens": self.tokens,
        }


def _citation(source_ref: str, excerpt: str) -> Citation | None:
    text = excerpt.strip()
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return Citation(
        citation_id=digest,
        source_ref=source_ref,
        excerpt=text,
        tokens=estimate_tokens(text),
    )


def citations_from_result(source_ref: str, payload: Mapping[str, Any]) -> tuple[Citation, ...]:
    """Turn one stored tool payload into quotable citations.

    Excerpts are the stored text, not a summary. A caller cannot pack a
    sentence the tool result did not contain.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("tool result must be an object")
    kind = payload.get("kind")
    found: list[Citation] = []
    if kind == "database":
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            raise TypeError("database rows must be a list")
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            encoded = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            citation = _citation(source_ref, encoded)
            if citation is not None:
                found.append(citation)
    elif kind == "network":
        hits = payload.get("hits") or []
        if not isinstance(hits, list):
            raise TypeError("network hits must be a list")
        for hit in hits:
            if not isinstance(hit, Mapping):
                continue
            excerpt = str(hit.get("snippet") or hit.get("title") or "")
            citation = _citation(source_ref, excerpt)
            if citation is not None and excerpt.strip() in str(hit.get("snippet") or hit.get("title") or ""):
                found.append(citation)
    elif kind == "sandbox":
        citation = _citation(source_ref, str(payload.get("stdout") or ""))
        if citation is not None:
            found.append(citation)
    elif kind == "artifact":
        return ()
    else:
        raise ValueError(f"unknown tool result kind {kind!r}")
    return tuple(found)


def pack_citations(citations: tuple[Citation, ...] | list[Citation], *, budget_tokens: int) -> tuple[Citation, ...]:
    """Keep whole citations, in order, until the budget is spent.

    A citation that does not fit is skipped. It is never sliced, because a
    sliced excerpt would no longer be the stored quote.
    """

    if isinstance(budget_tokens, bool) or not isinstance(budget_tokens, int) or budget_tokens < 0:
        raise ValueError("budget_tokens must be a non-negative integer")
    kept: list[Citation] = []
    used = 0
    for citation in citations:
        if used + citation.tokens > budget_tokens:
            continue
        kept.append(citation)
        used += citation.tokens
    return tuple(kept)


__all__ = ["Citation", "citations_from_result", "pack_citations"]
