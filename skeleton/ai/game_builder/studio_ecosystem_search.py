"""Deterministic local search of the canonical original-game production catalog.

Cheap metadata-only search by default. Deep search explicitly scans validated
source documents with a hard read budget derived from the *actual* catalog
size. No embeddings, network, unchecked file paths or publication claims.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .studio_ecosystem_catalog import (
    StudioEcosystemError, catalog_index, read_blueprint, ROOT,
)

WORD = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)
SECTIONS = ("narrative", "cast", "quest", "scene", "visual", "audio", "verification")


def _query_tokens(query: str) -> tuple[str, ...]:
    if (not isinstance(query, str) or not 1 <= len(query) <= 256
            or query != query.strip()
            or any(ord(c) < 32 for c in query)):
        raise StudioEcosystemError("invalid bounded catalog query")
    words = tuple(dict.fromkeys(token.casefold() for token in WORD.findall(query)))
    if not 1 <= len(words) <= 24 or any(len(word) > 64 for word in words):
        raise StudioEcosystemError("invalid search terms")
    return words


def search_blueprints(
    query: str, *, genre: str | None = None, biome: str | None = None,
    limit: int = 20, deep: bool = False, root=ROOT,
) -> dict[str, Any]:
    """Search all indexed projects deterministically; never certify gameplay.

    Ranking is based on source fields, not provider output. A deep search
    reads the eight authorized JSON docs per filtered entry via the canonical
    loader, and aborts on invalid source rather than silently skipping it.
    """
    tokens = _query_tokens(query)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise StudioEcosystemError("invalid result limit")
    if type(deep) is not bool:
        raise StudioEcosystemError("invalid deep search flag")
    for name, value in (("genre", genre), ("biome", biome)):
        if value is not None and (not isinstance(value, str) or len(value) > 80
                                  or not re.fullmatch(r"[a-z][a-z0-9_-]*", value)):
            raise StudioEcosystemError("invalid " + name + " filter")
    records = catalog_index(root=root)
    matches = []
    scanned = 0
    for rec in records:
        if (genre is not None and rec["genre"] != genre
                or biome is not None and rec["biome"] != biome):
            continue
        scanned += 1
        metadata = " ".join((rec["id"], rec["genre"], rec["biome"], rec["theme"])).casefold()
        # An exact identifier/genre/biome is weighted above any body match.
        fields = {"metadata": metadata}
        if deep:
            docs = read_blueprint(rec["id"], root=root)
            for section in SECTIONS:
                fields[section] = json.dumps(docs[section], sort_keys=True,
                                             ensure_ascii=True).casefold()
        missing = [word for word in tokens
                   if not any(word in content for content in fields.values())]
        if missing:
            continue
        hits = tuple(key for key, content in fields.items()
                     if any(word in content for word in tokens))
        score = sum(10 if word == rec["genre"] or word == rec["biome"]
                    else 6 if word in rec["id"]
                    else 3 if word in metadata else 1
                    for word in tokens)
        matches.append({
            "id": rec["id"], "genre": rec["genre"], "biome": rec["biome"],
            "score": score, "matched_sections": list(hits),
        })
    matches.sort(key=lambda x: (-x["score"], x["id"]))
    return {
        "schema": "skeleton.game_builder.studio_search_results.v1",
        "query": query,
        "deep_source_scan": deep,
        "scanned_projects": scanned,
        "matched_projects": len(matches),
        "returned_projects": len(matches[:limit]),
        "truncated_to_limit": len(matches) > limit,
        "results": matches[:limit],
        "release_certified": False,
    }
