"""CAS-authored original quest rules with replayed expedition preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_expedition import verify_expedition
from .harbor_crafting_quest_events import (
    MAX_BOARD_BYTES, build_quest_report, validate_quest_board,
    verify_quest_report,
)

SCHEMA = "skeleton.game.harbor.quest-edit.v1"
MAX_REVISION_BYTES = 196608
FIELDS = {
    "schema", "expedition", "before", "before_digest", "edits",
    "after", "after_digest", "preview", "revision_digest",
}
EDITABLE = {
    "trigger", "target", "requires_flags", "requires_sites",
    "requires_tokens", "min_energy", "reward", "required",
}


def edit_quest_board(expedition: Any, board: Any, edits: Any, *,
                     expected_expedition_digest: str, expected_board_digest: str,
                     preview_report: Any = None) -> dict[str, Any]:
    verify_expedition(expedition)
    before = validate_quest_board(board, expedition)
    if (expected_expedition_digest != expedition["expedition_digest"]
            or expected_board_digest != digest(before)):
        raise HarborError("stale quest authoring lease")
    if (not isinstance(edits, list) or not 1 <= len(edits) <= 16
            or len(canonical(edits)) > MAX_BOARD_BYTES):
        raise HarborError("invalid quest edits")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"id", "field", "value"}, "quest edit")
        name = _identifier(edit["id"], "quest edit id")
        quest = next((q for q in after["quests"] if q["id"] == name), None)
        if quest is None:
            raise HarborError("unknown quest edit target")
        field = edit["field"]
        if type(field) is not str or field not in EDITABLE:
            raise HarborError("unsupported quest edit field")
        quest[field] = deepcopy(edit["value"])
    after = validate_quest_board(after, expedition)
    preview = None
    if preview_report is not None:
        verify_quest_report(preview_report)
        if (preview_report["expedition"] != expedition
                or preview_report["board"] != before):
            raise HarborError("quest preview source mismatch")
        replay = build_quest_report(expedition, after)
        preview = {
            "before_report_digest": preview_report["report_digest"],
            "after_report_digest": replay["report_digest"],
            "before_reputation": preview_report["reputation"],
            "after_reputation": replay["reputation"],
            "before_complete": preview_report["complete"],
            "after_complete": replay["complete"],
        }
    revision = {
        "schema": SCHEMA, "expedition": deepcopy(expedition),
        "before": before, "before_digest": digest(before),
        "edits": deepcopy(edits), "after": after, "after_digest": digest(after),
        "preview": {"summary": preview, "report": deepcopy(preview_report)}
                   if preview_report is not None else None,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("quest revision exceeds byte limit")
    return revision


def verify_quest_edit(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "quest revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized quest revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("quest revision digest mismatch")
    preview = revision["preview"]
    if preview is not None:
        _keys(preview, {"summary", "report"}, "quest revision preview")
    rebuilt = edit_quest_board(
        revision["expedition"], revision["before"], revision["edits"],
        expected_expedition_digest=revision["expedition"]["expedition_digest"],
        expected_board_digest=revision["before_digest"],
        preview_report=preview["report"] if preview is not None else None,
    )
    if rebuilt != revision:
        raise HarborError("quest authoring replay mismatch")
    return {"board_digest": rebuilt["after_digest"],
            "quests": len(rebuilt["after"]["quests"]),
            "preview": deepcopy(preview["summary"]) if preview is not None else None}
