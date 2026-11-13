"""CAS beacon quest authoring with replayed consequence previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_beacon_quests import (
    MAX_REPORT_BYTES, build_beacon_quest_report, validate_beacon_quests,
    verify_beacon_quest_report,
)
from .harbor_crafting_beacons import verify_beacon_rescue

SCHEMA = "skeleton.game.harbor.beacon-quest-revision.v1"
MAX_REVISION_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {
    "schema", "source_report", "before", "after", "edits", "preview",
    "result", "before_digest", "after_digest", "revision_digest",
}
KINDS = {"reward", "target", "trigger", "requires"}


def edit_beacon_quests(rescue_report: Any, board: Any, edits: Any, *,
                       expected_board_digest: str,
                       preview_report: Any = None) -> dict[str, Any]:
    verify_beacon_rescue(rescue_report)
    original = validate_beacon_quests(board, rescue_report)
    if type(expected_board_digest) is not str or expected_board_digest != digest(original):
        raise HarborError("stale beacon quest authoring lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 24:
        raise HarborError("invalid beacon quest edit count")
    updated = deepcopy(original)
    normalized = []
    for edit in edits:
        _keys(edit, {"kind", "target", "value"}, "beacon quest edit")
        kind, target, value = edit["kind"], edit["target"], edit["value"]
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("unsupported beacon quest edit")
        name = _identifier(target, "beacon quest edit target")
        quest = next((item for item in updated["quests"] if item["id"] == name), None)
        if quest is None:
            raise HarborError("unknown beacon quest edit target")
        quest[kind] = value
        normalized.append(deepcopy(edit))
    validate_beacon_quests(updated, rescue_report)
    preview = None
    result = None
    if preview_report is not None:
        verify_beacon_quest_report(preview_report)
        if (preview_report["source_report"] != rescue_report
                or preview_report["board"] != original):
            raise HarborError("beacon quest preview source mismatch")
        preview = deepcopy(preview_report)
        result = build_beacon_quest_report(rescue_report, updated)
    revision = {
        "schema": SCHEMA, "source_report": deepcopy(rescue_report),
        "before": original, "after": updated, "edits": normalized,
        "preview": preview, "result": result,
        "before_digest": digest(original), "after_digest": digest(updated),
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("beacon quest revision exceeds byte budget")
    return revision


def verify_beacon_quest_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "beacon quest revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized beacon quest revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("beacon quest revision digest mismatch")
    rebuilt = edit_beacon_quests(
        revision["source_report"], revision["before"], revision["edits"],
        expected_board_digest=revision["before_digest"],
        preview_report=revision["preview"],
    )
    if rebuilt != revision:
        raise HarborError("beacon quest authoring replay mismatch")
    return {
        "verified": True, "after_digest": rebuilt["after_digest"],
        "preview_complete": None if rebuilt["result"] is None
                            else rebuilt["result"]["state"]["complete"],
    }
