"""CAS-protected original beacon editing with independent replayed previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_beacons import (
    MAX_REPORT_BYTES, build_beacon_rescue, validate_beacon_board,
    verify_beacon_rescue,
)

REVISION_SCHEMA = "skeleton.game.harbor.beacon-revision.v1"
MAX_REVISION_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {
    "schema", "source", "before", "after", "edits", "preview", "result",
    "before_digest", "after_digest", "revision_digest",
}
KINDS = {"power", "position", "requires", "repair-tool", "max-turns"}


def edit_beacons(source: Any, board: Any, edits: Any, *,
                 expected_board_digest: str,
                 preview_report: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    original = validate_beacon_board(board, world)
    if type(expected_board_digest) is not str or expected_board_digest != digest(original):
        raise HarborError("stale beacon authoring lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 24:
        raise HarborError("invalid beacon edit count")
    updated = deepcopy(original)
    normalized = []
    for edit in edits:
        _keys(edit, {"kind", "target", "value"}, "beacon edit")
        kind, target, value = edit["kind"], edit["target"], edit["value"]
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("unsupported beacon edit")
        if kind in {"repair-tool", "max-turns"}:
            if target != "board":
                raise HarborError("invalid beacon board edit target")
            updated["repair_tool" if kind == "repair-tool" else "max_turns"] = value
        else:
            name = _identifier(target, "beacon edit target")
            beacon = next((b for b in updated["beacons"] if b["id"] == name), None)
            if beacon is None:
                raise HarborError("unknown beacon edit target")
            beacon[{"power": "power", "position": "at", "requires": "requires"}[kind]] = value
        normalized.append(deepcopy(edit))
    validate_beacon_board(updated, world)
    preview = None
    result = None
    if preview_report is not None:
        verify_beacon_rescue(preview_report)
        if preview_report["source"] != world or preview_report["board"] != original:
            raise HarborError("beacon preview source mismatch")
        preview = deepcopy(preview_report)
        result = build_beacon_rescue(world, updated, preview["actions"])
    revision = {
        "schema": REVISION_SCHEMA, "source": world, "before": original,
        "after": updated, "edits": normalized, "preview": preview, "result": result,
        "before_digest": digest(original), "after_digest": digest(updated),
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("beacon revision exceeds byte budget")
    return revision


def verify_beacon_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "beacon revision")
    if revision["schema"] != REVISION_SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized beacon revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("beacon revision digest mismatch")
    rebuilt = edit_beacons(
        revision["source"], revision["before"], revision["edits"],
        expected_board_digest=revision["before_digest"],
        preview_report=revision["preview"],
    )
    if rebuilt != revision:
        raise HarborError("beacon authoring replay mismatch")
    return {
        "verified": True, "after_digest": revision["after_digest"],
        "preview_rescued": None if revision["result"] is None
                           else revision["result"]["state"]["rescued"],
    }
