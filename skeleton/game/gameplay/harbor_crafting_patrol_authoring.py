"""Transactional CAS patrol board authoring with optional source-to-replay preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_patrol import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_patrol, validate_patrol_board,
)

SCHEMA = "skeleton.game.harbor.patrol-authoring.v1"
MAX_REVISION_BYTES = MAX_REPORT_BYTES * 2
MAX_EDITS = 24
KEYS = {"schema", "source", "before", "after", "edits", "expected_digest",
        "before_digest", "after_digest", "preview_actions",
        "preview_before", "preview_after", "revision_digest"}


def _apply(source: Any, board: Any, edits: Any) -> dict[str, Any]:
    result = validate_patrol_board(board, source)
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("invalid patrol edit count")
    for edit in edits:
        if not isinstance(edit, dict) or type(edit.get("op")) is not str:
            raise HarborError("invalid patrol edit")
        op = edit["op"]
        if op == "set-alert-limit":
            _keys(edit, {"op", "value"}, "patrol alert edit")
            result["alert_limit"] = _integer(edit["value"], 1, 12, "patrol alert limit")
        elif op == "set-guard-sight":
            _keys(edit, {"op", "id", "value"}, "patrol guard edit")
            name = _identifier(edit["id"], "patrol guard id")
            guard = next((g for g in result["guards"] if g["id"] == name), None)
            if guard is None:
                raise HarborError("unknown patrol guard edit target")
            guard["sight"] = _integer(edit["value"], 0, 3, "patrol guard sight")
        elif op == "set-objective-reward":
            _keys(edit, {"op", "id", "value"}, "patrol objective edit")
            name = _identifier(edit["id"], "patrol objective id")
            objective = next((o for o in result["objectives"] if o["id"] == name), None)
            if objective is None:
                raise HarborError("unknown patrol objective edit target")
            objective["reward"] = _integer(edit["value"], 1, 100, "patrol objective reward")
        else:
            raise HarborError("unsupported patrol edit operation")
    return validate_patrol_board(result, source)


def edit_patrol_board(source: Any, board: Any, edits: Any, *,
                      expected_digest: str,
                      preview_actions: Any = None) -> dict[str, Any]:
    before = validate_patrol_board(board, source)
    before_digest = digest(before)
    if type(expected_digest) is not str or expected_digest != before_digest:
        raise HarborError("stale patrol board CAS lease")
    after = _apply(source, before, edits)
    if preview_actions is not None and not isinstance(preview_actions, list):
        raise HarborError("invalid patrol preview actions")
    preview_before = (build_patrol(source, before, preview_actions)
                      if preview_actions is not None else None)
    preview_after = (build_patrol(source, after, preview_actions)
                     if preview_actions is not None else None)
    revision = {
        "schema": SCHEMA, "source": deepcopy(source), "before": before, "after": after,
        "edits": deepcopy(edits), "expected_digest": expected_digest,
        "before_digest": before_digest, "after_digest": digest(after),
        "preview_actions": deepcopy(preview_actions),
        "preview_before": preview_before, "preview_after": preview_after,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("patrol authoring revision exceeds byte budget")
    return revision


def verify_patrol_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, KEYS, "patrol authoring revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized patrol revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("patrol revision digest mismatch")
    rebuilt = edit_patrol_board(
        revision["source"], revision["before"], revision["edits"],
        expected_digest=revision["expected_digest"],
        preview_actions=revision["preview_actions"],
    )
    if rebuilt != revision:
        raise HarborError("patrol authoring replay mismatch")
    return deepcopy(revision["after"])
