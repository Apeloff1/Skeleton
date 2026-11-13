"""Optimistic, source-bound transactional editor for playable harbor mission boards.

A revision is an independently replayable change to authored mission data.
The optional preview is generated only by verified canonical gameplay replay.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, validate_source, verify_bundle,
)
from .harbor_crafting_missions import mission_report, validate_board

REVISION_SCHEMA = "skeleton.game.harbor.mission-revision.v1"
MAX_OPERATIONS = 24
OPERATIONS = {
    "add_mission": {"op", "mission"},
    "remove_mission": {"op", "id"},
    "replace_mission": {"op", "id", "mission"},
    "set_points": {"op", "id", "value"},
    "set_deadline": {"op", "id", "value"},
    "set_requires": {"op", "id", "requires"},
    "append_objective": {"op", "id", "objective"},
    "replace_objective": {"op", "id", "index", "objective"},
    "remove_objective": {"op", "id", "index"},
}


def _edit(board: dict[str, Any], edit: Any) -> tuple[Any, ...]:
    if not isinstance(edit, dict):
        raise HarborError("mission edit must be an object")
    kind = edit.get("op")
    if type(kind) is not str or kind not in OPERATIONS:
        raise HarborError("unknown mission edit operation")
    _keys(edit, OPERATIONS[kind], "mission edit")
    if kind == "add_mission":
        mission = edit["mission"]
        if not isinstance(mission, dict):
            raise HarborError("new mission must be an object")
        name = _identifier(mission.get("id"), "new mission id")
        board["missions"].append(deepcopy(mission))
        return ("mission", name)
    name = _identifier(edit["id"], "mission edit id")
    index = next((i for i, m in enumerate(board["missions"]) if m["id"] == name), None)
    if index is None:
        raise HarborError("mission edit target not found")
    target = board["missions"][index]
    if kind == "remove_mission":
        board["missions"].pop(index)
        return ("mission", name)
    if kind == "replace_mission":
        replacement = edit["mission"]
        if not isinstance(replacement, dict) or replacement.get("id") != name:
            raise HarborError("replacement mission id mismatch")
        board["missions"][index] = deepcopy(replacement)
        return ("mission", name)
    if kind in ("set_points", "set_deadline"):
        key = "points" if kind == "set_points" else "deadline"
        target[key] = edit["value"]
        return (name, key)
    if kind == "set_requires":
        target["requires"] = deepcopy(edit["requires"])
        return (name, "requires")
    objectives = target["objectives"]
    if kind == "append_objective":
        objectives.append(deepcopy(edit["objective"]))
        return (name, "objective", len(objectives) - 1)
    objective_index = _integer(edit["index"], 0, len(objectives) - 1, "objective index")
    if kind == "replace_objective":
        objectives[objective_index] = deepcopy(edit["objective"])
    else:
        objectives.pop(objective_index)
    return (name, "objective", objective_index)


def author_mission_revision(
    board: Any, source: Any, operations: Any, *,
    expected_board_digest: str, preview_bundle: Any = None,
) -> dict[str, Any]:
    world = validate_source(source)
    parent = validate_board(board, world)
    previous_digest = digest(parent)
    if type(expected_board_digest) is not str or expected_board_digest != previous_digest:
        raise HarborError("stale mission board digest")
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise HarborError("invalid mission edit count")
    edited = deepcopy(parent)
    targets: set[tuple[Any, ...]] = set()
    for operation in operations:
        target = _edit(edited, operation)
        if target in targets:
            raise HarborError("duplicate mission edit target")
        targets.add(target)
    result = validate_board(edited, world)
    if result == parent:
        raise HarborError("mission revision must change authored source")
    preview = None
    if preview_bundle is not None:
        verify_bundle(preview_bundle)
        if preview_bundle["source_digest"] != digest(world):
            raise HarborError("mission preview source mismatch")
        preview = mission_report(preview_bundle, result)
    revision = {
        "schema": REVISION_SCHEMA,
        "source": world,
        "source_digest": digest(world),
        "parent": parent,
        "parent_digest": previous_digest,
        "operations": deepcopy(operations),
        "board": result,
        "board_digest": digest(result),
        "preview": preview,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_BUNDLE_BYTES * 2:
        raise HarborError("mission revision exceeds byte limit")
    return revision


def verify_mission_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, {
        "schema", "source", "source_digest", "parent", "parent_digest",
        "operations", "board", "board_digest", "preview", "revision_digest",
    }, "mission revision")
    if revision["schema"] != REVISION_SCHEMA or len(canonical(revision)) > MAX_BUNDLE_BYTES * 2:
        raise HarborError("unsupported or oversized mission revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("mission revision digest mismatch")
    if revision["source_digest"] != digest(revision["source"]):
        raise HarborError("mission revision source digest mismatch")
    preview = revision["preview"]
    if preview is not None and not isinstance(preview, dict):
        raise HarborError("invalid mission preview")
    preview_bundle = None if preview is None else preview.get("bundle")
    if preview is not None and preview_bundle is None:
        raise HarborError("missing mission preview bundle")
    recreated = author_mission_revision(
        revision["parent"], revision["source"], revision["operations"],
        expected_board_digest=revision["parent_digest"],
        preview_bundle=preview_bundle,
    )
    if recreated != revision:
        raise HarborError("mission revision replay mismatch")
    return deepcopy(recreated["board"])
