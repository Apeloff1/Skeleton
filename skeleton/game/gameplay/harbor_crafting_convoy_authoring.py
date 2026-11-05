"""Transactional convoy route, encounter and difficulty authoring with replay previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_convoy, validate_convoy_board,
    verify_convoy,
)

REVISION_SCHEMA = "skeleton.game.harbor.convoy-revision.v1"
MAX_REVISION_BYTES = MAX_REPORT_BYTES * 2
KINDS = {"hull", "max-turns", "weapon", "waypoint", "encounter-strength", "encounter-reward"}
FIELDS = {
    "schema", "source", "before", "after", "edits", "preview",
    "result", "before_digest", "after_digest", "revision_digest",
}


def edit_convoy_board(source: Any, board: Any, edits: Any, *,
                      expected_board_digest: str,
                      preview_report: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    original = validate_convoy_board(board, world)
    if type(expected_board_digest) is not str or expected_board_digest != digest(original):
        raise HarborError("stale convoy authoring lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 24:
        raise HarborError("invalid convoy edit count")
    updated = deepcopy(original)
    normalized = []
    for edit in edits:
        _keys(edit, {"kind", "target", "value"}, "convoy edit")
        kind, target, value = edit["kind"], edit["target"], edit["value"]
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("unsupported convoy edit")
        if type(target) is not str:
            raise HarborError("invalid convoy edit target")
        if kind in {"hull", "max-turns", "weapon"}:
            if target != "board":
                raise HarborError("invalid convoy board target")
            updated[{"hull": "hull", "max-turns": "max_turns", "weapon": "weapon_item"}[kind]] = value
        elif kind == "waypoint":
            if not target.isdecimal() or str(int(target)) != target:
                raise HarborError("invalid convoy waypoint index")
            index = int(target)
            if not 0 <= index < len(updated["route"]):
                raise HarborError("unknown convoy waypoint")
            updated["route"][index] = value
        else:
            name = _identifier(target, "convoy encounter target")
            encounter = next((item for item in updated["encounters"] if item["id"] == name), None)
            if encounter is None:
                raise HarborError("unknown convoy encounter")
            encounter["strength" if kind == "encounter-strength" else "reward"] = value
        normalized.append(deepcopy(edit))
    validate_convoy_board(updated, world)
    preview = None
    result = None
    if preview_report is not None:
        verify_convoy(preview_report)
        if (preview_report["source"] != world
                or preview_report["board"] != original):
            raise HarborError("convoy preview source mismatch")
        preview = deepcopy(preview_report)
        result = build_convoy(world, updated, preview["actions"])
    revision = {
        "schema": REVISION_SCHEMA, "source": world,
        "before": original, "after": updated, "edits": normalized,
        "preview": preview, "result": result,
        "before_digest": digest(original), "after_digest": digest(updated),
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("convoy authoring revision exceeds byte budget")
    return revision


def verify_convoy_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "convoy revision")
    if (revision["schema"] != REVISION_SCHEMA
            or len(canonical(revision)) > MAX_REVISION_BYTES):
        raise HarborError("unsupported or oversized convoy revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("convoy revision digest mismatch")
    rebuilt = edit_convoy_board(
        revision["source"], revision["before"], revision["edits"],
        expected_board_digest=revision["before_digest"],
        preview_report=revision["preview"],
    )
    if rebuilt != revision:
        raise HarborError("convoy authoring replay mismatch")
    return {
        "verified": True,
        "before_digest": revision["before_digest"],
        "after_digest": revision["after_digest"],
        "preview_complete": None if revision["result"] is None
                            else revision["result"]["state"]["complete"],
    }
