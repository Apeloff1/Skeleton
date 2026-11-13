"""CAS-protected merchant dialogue editing and source-bound gameplay preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_dialogue import (
    MAX_BOARD_BYTES, build_dialogue_game, validate_dialogue_board,
    verify_dialogue_game,
)

SCHEMA = "skeleton.game.harbor.dialogue-edit.v1"
MAX_REVISION_BYTES = 196608
FIELDS = {
    "schema", "source", "before", "before_digest", "edits", "after",
    "after_digest", "preview", "revision_digest",
}


def edit_dialogue(source: Any, board: Any, edits: Any, *,
                  expected_source_digest: str, expected_board_digest: str,
                  preview_report: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    before = validate_dialogue_board(board, world)
    if expected_source_digest != digest(world) or expected_board_digest != digest(before):
        raise HarborError("stale dialogue authoring lease")
    if (not isinstance(edits, list) or not 1 <= len(edits) <= 16
            or len(canonical(edits)) > MAX_BOARD_BYTES):
        raise HarborError("invalid dialogue edits")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"node", "choice", "field", "value"}, "dialogue edit")
        name = _identifier(edit["node"], "dialogue edit node")
        node = next((n for n in after["nodes"] if n["id"] == name), None)
        if node is None:
            raise HarborError("unknown dialogue edit node")
        field = edit["field"]
        if type(field) is not str:
            raise HarborError("invalid dialogue edit field")
        if field in ("min_trust", "requires") and edit["choice"] is None:
            node[field] = deepcopy(edit["value"])
        elif field in ("trust_delta", "grant_flag"):
            choice_id = _identifier(edit["choice"], "dialogue edit choice")
            choice = next((c for c in node["choices"] if c["id"] == choice_id), None)
            if choice is None:
                raise HarborError("unknown dialogue edit choice")
            choice[field] = deepcopy(edit["value"])
        else:
            raise HarborError("unsupported dialogue edit field")
    after = validate_dialogue_board(after, world)
    preview = None
    if preview_report is not None:
        verify_dialogue_game(preview_report)
        if (preview_report["source_digest"] != digest(world)
                or preview_report["board"] != before):
            raise HarborError("dialogue preview source mismatch")
        replay = build_dialogue_game(world, after, preview_report["input_actions"])
        preview = {
            "report": deepcopy(preview_report),
            "before_trust": preview_report["trust"],
            "after_trust": replay["trust"],
            "before_digest": preview_report["report_digest"],
            "after_digest": replay["report_digest"],
        }
    revision = {
        "schema": SCHEMA, "source": world, "before": before,
        "before_digest": digest(before), "edits": deepcopy(edits),
        "after": after, "after_digest": digest(after), "preview": preview,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("dialogue revision exceeds byte limit")
    return revision


def verify_dialogue_edit(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "dialogue revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized dialogue revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("dialogue revision digest mismatch")
    preview = revision["preview"]
    if preview is not None:
        _keys(preview, {"report", "before_trust", "after_trust", "before_digest",
                        "after_digest"}, "dialogue revision preview")
    rebuilt = edit_dialogue(
        revision["source"], revision["before"], revision["edits"],
        expected_source_digest=digest(revision["source"]),
        expected_board_digest=revision["before_digest"],
        preview_report=preview["report"] if preview is not None else None,
    )
    if rebuilt != revision:
        raise HarborError("dialogue authoring replay mismatch")
    return {
        "board_digest": rebuilt["after_digest"],
        "nodes": len(rebuilt["after"]["nodes"]),
        "preview_trust": preview["after_trust"] if preview is not None else None,
    }
