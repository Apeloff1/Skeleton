"""Transactional source editing for replay-verified Lantern Quay championships.

A season revision is an immutable, verifiable edit transaction. When an existing
player save is supplied, earned rounds and their scoring rules are locked, and
the preview is recomputed against the revised season before publication.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _keys, canonical, digest,
    validate_source,
)
from .harbor_crafting_season import (
    MAX_RECORD_BYTES, MAX_ROUNDS, MAX_SEASON_BYTES,
    build_season, validate_season, verify_season_record,
)

REVISION_SCHEMA = "skeleton.game.harbor.season-revision.v1"
MAX_EDITS = 16
MAX_REVISION_BYTES = MAX_RECORD_BYTES * 2 + MAX_SEASON_BYTES
FIELDS = {
    "schema", "source", "source_digest", "base_season",
    "base_season_digest", "edits", "season", "season_digest",
    "preview_record", "preview_result", "revision_digest",
}
SHAPES = {
    "set_points": {"op", "points"},
    "replace_round": {"op", "id", "course"},
    "append_round": {"op", "id", "course"},
    "remove_last": {"op", "id"},
}


def _apply(base: dict[str, Any], edits: Any) -> dict[str, Any]:
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("invalid season edit count")
    if len(canonical(edits)) > MAX_SEASON_BYTES:
        raise HarborError("season edits exceed byte limit")
    season = deepcopy(base)
    for edit in edits:
        if not isinstance(edit, dict):
            raise HarborError("invalid season edit")
        op = edit.get("op")
        if type(op) is not str or op not in SHAPES or set(edit) != SHAPES[op]:
            raise HarborError("unsupported season edit shape")
        if op == "set_points":
            season["points"] = deepcopy(edit["points"])
            continue
        name = _identifier(edit["id"], "edited season round id")
        index = next(
            (i for i, item in enumerate(season["rounds"]) if item["id"] == name),
            None,
        )
        if op == "append_round":
            if index is not None or len(season["rounds"]) >= MAX_ROUNDS:
                raise HarborError("duplicate or excessive season round")
            season["rounds"].append({"id": name, "course": deepcopy(edit["course"])})
        elif op == "replace_round":
            if index is None:
                raise HarborError("missing season round for replacement")
            season["rounds"][index] = {"id": name, "course": deepcopy(edit["course"])}
        elif op == "remove_last":
            if index is None or index != len(season["rounds"]) - 1:
                raise HarborError("only the final season round may be removed")
            season["rounds"].pop()
    return season


def author_season_revision(
    source: Any, base_season: Any, edits: Any, *,
    expected_source_digest: str, expected_season_digest: str,
    preview_record: Any = None,
) -> dict[str, Any]:
    """Atomically validate source, CAS leases, every edit and earned-save preview."""
    world = validate_source(source)
    base = validate_season(base_season, world)
    if expected_source_digest != digest(world):
        raise HarborError("stale season authoring source")
    if expected_season_digest != digest(base):
        raise HarborError("stale season authoring base")
    revised = validate_season(_apply(base, edits), world)
    preview = None
    stored = None
    if preview_record is not None:
        verify_season_record(preview_record)
        if (
            preview_record["source_digest"] != digest(world)
            or preview_record["season_digest"] != digest(base)
        ):
            raise HarborError("season preview source or base mismatch")
        earned = len(preview_record["results"])
        if earned > len(revised["rounds"]):
            raise HarborError("cannot remove earned season rounds")
        if earned and revised["points"] != base["points"]:
            raise HarborError("cannot rescore earned season rounds")
        if revised["rounds"][:earned] != base["rounds"][:earned]:
            raise HarborError("cannot rewrite earned season rounds")
        bundles = [entry["report"]["bundle"] for entry in preview_record["results"]]
        preview = build_season(world, revised, bundles)
        stored = deepcopy(preview_record)
    revision = {
        "schema": REVISION_SCHEMA, "source": world, "source_digest": digest(world),
        "base_season": base, "base_season_digest": digest(base),
        "edits": deepcopy(edits), "season": revised,
        "season_digest": digest(revised), "preview_record": stored,
        "preview_result": preview,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("season revision exceeds byte limit")
    return revision


def verify_season_revision(value: Any) -> dict[str, Any]:
    """Re-run the entire authoring transaction, including game replay previews."""
    _keys(value, FIELDS, "season revision")
    if value["schema"] != REVISION_SCHEMA or len(canonical(value)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized season revision")
    if value["revision_digest"] != digest({
        k: v for k, v in value.items() if k != "revision_digest"
    }):
        raise HarborError("season revision digest mismatch")
    rebuilt = author_season_revision(
        value["source"], value["base_season"], value["edits"],
        expected_source_digest=value["source_digest"],
        expected_season_digest=value["base_season_digest"],
        preview_record=value["preview_record"],
    )
    if rebuilt != value:
        raise HarborError("season revision replay mismatch")
    return {
        "season": deepcopy(rebuilt["season"]),
        "season_digest": rebuilt["season_digest"],
        "preview": deepcopy(rebuilt["preview_result"]),
    }
