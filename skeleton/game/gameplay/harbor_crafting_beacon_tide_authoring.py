"""CAS tide editor with source-bound replayed preview of hazard consequences."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_beacon_tides import (
    MAX_REPORT_BYTES, build_beacon_tide_report, validate_beacon_tides,
    verify_beacon_tide_report,
)

SCHEMA = "skeleton.game.harbor.beacon-tide-revision.v1"
MAX_REVISION_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {
    "schema", "source", "beacon_board", "before", "after", "edits",
    "preview", "result", "before_digest", "after_digest", "revision_digest",
}
KINDS = {"period", "high_ticks", "hazard_tiles", "stamina", "drain", "rest_gain", "rest_at"}


def edit_beacon_tides(source: Any, beacon_board: Any, tide_board: Any, edits: Any, *,
                      expected_board_digest: str,
                      preview_report: Any = None) -> dict[str, Any]:
    original = validate_beacon_tides(tide_board, source, beacon_board)
    if type(expected_board_digest) is not str or expected_board_digest != digest(original):
        raise HarborError("stale beacon tide authoring lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 24:
        raise HarborError("invalid beacon tide edit count")
    updated = deepcopy(original)
    normalized = []
    for edit in edits:
        _keys(edit, {"kind", "value"}, "beacon tide edit")
        if type(edit["kind"]) is not str or edit["kind"] not in KINDS:
            raise HarborError("unsupported beacon tide edit")
        updated[edit["kind"]] = edit["value"]
        normalized.append(deepcopy(edit))
    validate_beacon_tides(updated, source, beacon_board)
    preview = None
    result = None
    if preview_report is not None:
        verify_beacon_tide_report(preview_report)
        if (preview_report["source"] != source
                or preview_report["beacon_board"] != beacon_board
                or preview_report["tide_board"] != original):
            raise HarborError("beacon tide preview source mismatch")
        preview = deepcopy(preview_report)
        result = build_beacon_tide_report(
            source, beacon_board, updated, preview["actions"],
        )
    revision = {
        "schema": SCHEMA, "source": deepcopy(source),
        "beacon_board": deepcopy(beacon_board),
        "before": original, "after": updated, "edits": normalized,
        "preview": preview, "result": result,
        "before_digest": digest(original), "after_digest": digest(updated),
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("beacon tide revision exceeds byte budget")
    return revision


def verify_beacon_tide_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "beacon tide revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized tide revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("beacon tide revision digest mismatch")
    rebuilt = edit_beacon_tides(
        revision["source"], revision["beacon_board"], revision["before"],
        revision["edits"], expected_board_digest=revision["before_digest"],
        preview_report=revision["preview"],
    )
    if rebuilt != revision:
        raise HarborError("beacon tide authoring replay mismatch")
    return {
        "verified": True, "after_digest": rebuilt["after_digest"],
        "preview_rescued": None if rebuilt["result"] is None
                           else rebuilt["result"]["state"]["rescued"],
    }
