"""Deterministic source-cited search for original studio production briefs.

Metadata queries are cheap. Deep source search streams eight canonical authored
documents per candidate, validates each through the existing owner and records
exact matching sections; never executes content, uses credentials or mutates source.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .studio_ecosystem_catalog import (
    ROOT, SECTIONS, StudioEcosystemError, list_blueprints, read_blueprint,
)

_TOKENS = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> tuple[str, ...]:
    if not isinstance(text, str) or not 1 <= len(text) <= 192:
        raise StudioEcosystemError("search phrase must contain 1..192 characters")
    if any(ord(ch) < 32 for ch in text):
        raise StudioEcosystemError("unsafe search control character")
    result = tuple(dict.fromkeys(_TOKENS.findall(text.casefold().replace("_", " "))))
    if not result or len(result) > 16:
        raise StudioEcosystemError("unsupported empty or oversized search terms")
    return result


def search_blueprints(
    query: str, *, genre: str | None = None, biome: str | None = None,
    deep: bool = False, limit: int = 32, root: Path = ROOT,
) -> tuple[dict[str, Any], ...]:
    """Return stable ranked previews with source-section hit receipts.

    Search is an original design-discovery capability, NOT an inference model.
    Deep reads are opt-in because they touch all selected original JSON sources.
    """
    terms = _terms(query)
    if type(deep) is not bool or type(limit) is not int or limit <= 0:
        raise StudioEcosystemError("invalid search configuration")
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for record in list_blueprints(genre=genre, biome=biome, root=root):
        metadata = " ".join(record.values()).lower().replace("_", " ")
        body = [("metadata", metadata)]
        if deep:
            parts = read_blueprint(record["id"], root=root)
            body.extend((section, json.dumps(parts[section], sort_keys=True,
                                             ensure_ascii=True).lower().replace("_", " "))
                        for section in SECTIONS)
        hits = {term: [section for section, value in body if term in value]
                for term in terms}
        if not all(hits.values()):
            continue
        sections = [section for section, _ in body
                    if any(section in match for match in hits.values())]
        score = sum((8 if term in metadata else 1) +
                    max(0, len(hits[term]) - 1)
                    for term in terms)
        ranked.append((-score, record["id"], {
            "project_id": record["id"],
            "genre": record["genre"], "biome": record["biome"],
            "theme": record["theme"],
            "score": score,
            "matched_sections": sections,
            "release_certified": False,
        }))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in ranked[:limit])


__all__ = ["search_blueprints"]
