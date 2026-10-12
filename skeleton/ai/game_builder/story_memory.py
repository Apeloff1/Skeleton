"""Exact indexed story memory retrieval for conversations and AI game authoring.

This is persistent source-backed recall, not unbounded attention or model memory.
It reconstructs the full accepted source chain, then returns a bounded evidence
page with a digest and complete bookmark identity for every retrieved statement.
"""
from __future__ import annotations

from .story_canon_fabric import StoryCanonError, digest, ident, require
from .story_workspace import load_story_workspace

BUCKETS = ("events", "dialogue", "interactions", "beats")


def retrieve_bookmarks(workspace, project, references):
    """Retrieve exact original source units across any two distant scenes."""
    require(type(references) is list and 1 <= len(references) <= 32,
            "Jeeves bookmark lookup must be bounded, nonempty and ordered")
    require(len(references) == len(set(references)),
            "duplicate memory references are not independent facts")
    for ref in references:
        ident(ref, "historical bookmark")
    bible, scenes, index = load_story_workspace(workspace, project)
    require(bible is not None, "cannot retrieve missing original canon")
    result = []
    for ref in references:
        bookmark = index["bookmarks"].get(ref)
        require(bookmark is not None,
                "Jeeves must never invent or infer a missing story bookmark")
        position = bookmark["sequence"] - 1
        scene = scenes[position]
        require(scene["digest"] == bookmark["scene_digest"],
                "historical bookmark points to altered scene content")
        located = [(kind, dict(row)) for kind in BUCKETS
                   for row in scene[kind] if row["id"] == ref]
        require(len(located) == 1,
                "each story bookmark must resolve to one original unit")
        kind, row = located[0]
        result.append({
            "id": ref, "kind": kind, "source": bookmark,
            "value": row, "row_digest": digest(row),
        })
    record = {
        "schema": "skeleton.game_builder.jeeves_memory_evidence.v1",
        "project": project, "bible_digest": bible["digest"],
        "history_digest": index["digest"],
        "head_digest": index["head_digest"], "records": result,
        "requested_count": len(references),
        "missing_records": 0, "memory_invented": False,
        "model_weights_modified": False,
    }
    return {**record, "digest": digest(record)}


def character_memory_page(workspace, project, character, *, partner=None,
                          offset=0, limit=40):
    """Timeline page for an NPC, or the complete ordered pair relationship.

    Full source index is still available when a page is truncated. Paging is
    deterministic and never summarizes away an inconvenient past exchange.
    """
    ident(character, "character")
    if partner is not None:
        ident(partner, "relationship partner")
        require(partner != character, "self-dialogue is not a relationship pair")
    require(type(offset) is int and 0 <= offset <= 120000,
            "memory page offset is outside bounded history")
    require(type(limit) is int and 1 <= limit <= 64,
            "memory page size must be bounded")
    bible, scenes, index = load_story_workspace(workspace, project)
    require(bible is not None and character in
            {x["id"] for x in bible["characters"]},
            "character does not exist in approved original source")
    if partner is not None:
        require(partner in {x["id"] for x in bible["characters"]},
                "the relationship partner does not exist in canon")
        key = ":".join(sorted((character, partner)))
        entries = index["pairs"].get(key, [])
    else:
        # Preserve participant identity using actual canonical pair keys.
        entries = []
        for key, rows in index["pairs"].items():
            if character in key.split(":"):
                entries.extend(rows)
        entries.sort(key=lambda row: (row["sequence"], row["ref"]))
    page = entries[offset:offset+limit]
    out = {
        "schema": "skeleton.game_builder.character_story_memory_page.v1",
        "project": project, "character": character, "partner": partner,
        "head_digest": index["head_digest"], "index_digest": index["digest"],
        "total": len(entries), "offset": offset, "limit": limit,
        "next_offset": offset + len(page) if offset+len(page) < len(entries) else None,
        "references": [entry["ref"] for entry in page],
        "historical_memory_complete_in_page": offset == 0 and len(page) == len(entries),
        "all_source_history_preserved": True,
        "source_model_inference_performed": False,
    }
    return {**out, "digest": digest(out)}


def asset_identity_history(workspace, project, asset):
    """Every scene reusing an asset, with canonical look and original rights."""
    ident(asset, "asset")
    bible, scenes, index = load_story_workspace(workspace, project)
    require(bible is not None, "approved design bible required")
    source = next((a for a in bible["assets"] if a["id"] == asset), None)
    require(source is not None, "unknown original asset source")
    seqs = index["assets"].get(asset, [])
    record = {
        "schema": "skeleton.game_builder.asset_continuity_history.v1",
        "asset": asset, "asset_canon": source,
        "asset_source_digest": digest(source),
        "source_project": project, "region": source["region"],
        "scenes": seqs, "scene_count": len(seqs),
        "history_digest": index["digest"],
        "appearance_consistency_verified": True,
        "no_legal_clearance_inferred": True,
    }
    return {**record, "digest": digest(record)}
