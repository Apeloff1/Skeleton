"""CAS-protected patrol quest editor with full replayed reward preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_patrol_quests import (
    MAX_LEDGER_BYTES, MAX_QUESTS, build_patrol_quests, validate_patrol_quest_board,
)

SCHEMA = "skeleton.game.harbor.patrol-quest-authoring.v1"
MAX_REVISION_BYTES = MAX_LEDGER_BYTES * 2
MAX_EDITS = 24
KEYS = {"schema", "patrol", "before", "after", "edits",
        "expected_digest", "before_digest", "after_digest",
        "preview_before", "preview_after", "revision_digest"}


def _apply(patrol: Any, board: Any, edits: Any) -> dict[str, Any]:
    result = validate_patrol_quest_board(board, patrol)
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("invalid patrol quest edit count")
    for edit in edits:
        if not isinstance(edit, dict) or type(edit.get("op")) is not str:
            raise HarborError("invalid patrol quest edit")
        op = edit["op"]
        if op == "set-reward":
            _keys(edit, {"op", "id", "value"}, "patrol quest reward edit")
        elif op == "set-requires":
            _keys(edit, {"op", "id", "value"}, "patrol quest prerequisite edit")
        else:
            raise HarborError("unsupported patrol quest edit")
        name = _identifier(edit["id"], "patrol quest edit id")
        quest = next((q for q in result["quests"] if q["id"] == name), None)
        if quest is None:
            raise HarborError("unknown patrol quest edit target")
        if op == "set-reward":
            quest["reward"] = _integer(edit["value"], 1, 100, "patrol quest reward")
        else:
            value = edit["value"]
            if not isinstance(value, list) or len(value) > MAX_QUESTS:
                raise HarborError("invalid patrol quest prerequisites")
            quest["requires"] = deepcopy(value)
    return validate_patrol_quest_board(result, patrol)


def edit_patrol_quests(patrol: Any, board: Any, edits: Any, *,
                       expected_digest: str) -> dict[str, Any]:
    before = validate_patrol_quest_board(board, patrol)
    before_digest = digest(before)
    if type(expected_digest) is not str or expected_digest != before_digest:
        raise HarborError("stale patrol quest CAS lease")
    after = _apply(patrol, before, edits)
    preview_before = build_patrol_quests(patrol, before)
    preview_after = build_patrol_quests(patrol, after)
    result = {"schema": SCHEMA, "patrol": deepcopy(patrol),
              "before": before, "after": after, "edits": deepcopy(edits),
              "expected_digest": expected_digest,
              "before_digest": before_digest, "after_digest": digest(after),
              "preview_before": preview_before, "preview_after": preview_after}
    result["revision_digest"] = digest(result)
    if len(canonical(result)) > MAX_REVISION_BYTES:
        raise HarborError("patrol quest revision exceeds byte budget")
    return result


def verify_patrol_quest_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, KEYS, "patrol quest revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized patrol quest revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("patrol quest revision digest mismatch")
    rebuilt = edit_patrol_quests(
        revision["patrol"], revision["before"], revision["edits"],
        expected_digest=revision["expected_digest"],
    )
    if rebuilt != revision:
        raise HarborError("patrol quest revision replay mismatch")
    return deepcopy(revision["after"])
