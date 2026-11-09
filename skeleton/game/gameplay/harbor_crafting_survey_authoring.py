"""CAS-protected survey source editing with replayed gameplay preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, _identifier, _keys, canonical, digest, validate_source,
)
from .harbor_crafting_survey import (
    MAX_BOARD_BYTES, build_survey, validate_board, verify_survey,
)

SCHEMA = "skeleton.game.harbor.survey-edit.v1"
MAX_REVISION_BYTES = 196608
FIELDS = {
    "schema", "source", "before", "before_digest", "edits",
    "after", "after_digest", "preview", "revision_digest",
}


def edit_survey(source: Any, board: Any, edits: Any, *,
                expected_source_digest: str, expected_board_digest: str,
                preview_report: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    before = validate_board(board, world)
    if (expected_source_digest != digest(world)
            or expected_board_digest != digest(before)):
        raise HarborError("stale survey authoring lease")
    if (not isinstance(edits, list) or not 1 <= len(edits) <= 16
            or len(canonical(edits)) > MAX_BOARD_BYTES):
        raise HarborError("invalid survey edits")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"id", "field", "value"}, "survey edit")
        name = _identifier(edit["id"], "survey edit id")
        site = next((s for s in after["sites"] if s["id"] == name), None)
        if site is None:
            raise HarborError("unknown survey site")
        if type(edit["field"]) is not str or edit["field"] not in ("points", "required", "at"):
            raise HarborError("unsupported survey edit field")
        site[edit["field"]] = deepcopy(edit["value"])
    after = validate_board(after, world)
    preview = None
    if preview_report is not None:
        verify_survey(preview_report)
        if (preview_report["source_digest"] != digest(world)
                or preview_report["board"] != before):
            raise HarborError("survey preview source or board mismatch")
        actions = [event["action"] for event in preview_report["bundle"]["events"]]
        updated = build_survey(world, after, actions)
        preview = {
            "before_report_digest": preview_report["report_digest"],
            "after_report_digest": updated["report_digest"],
            "before_score": preview_report["score"],
            "after_score": updated["score"],
            "before_complete": preview_report["complete"],
            "after_complete": updated["complete"],
        }
    revision = {
        "schema": SCHEMA, "source": world, "before": before,
        "before_digest": digest(before), "edits": deepcopy(edits),
        "after": after, "after_digest": digest(after),
        "preview": preview,
    }
    # Preview evidence must be included for deterministic independent replay.
    if preview_report is not None:
        revision["preview"] = {"summary": preview, "report": deepcopy(preview_report)}
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("survey revision exceeds byte limit")
    return revision


def verify_survey_edit(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "survey revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized survey revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("survey revision digest mismatch")
    preview = revision["preview"]
    if preview is not None:
        _keys(preview, {"summary", "report"}, "survey revision preview")
    rebuilt = edit_survey(
        revision["source"], revision["before"], revision["edits"],
        expected_source_digest=digest(revision["source"]),
        expected_board_digest=revision["before_digest"],
        preview_report=preview["report"] if preview is not None else None,
    )
    if rebuilt != revision:
        raise HarborError("survey authoring replay mismatch")
    return {"board_digest": rebuilt["after_digest"],
            "sites": len(rebuilt["after"]["sites"]),
            "preview": deepcopy(preview["summary"]) if preview is not None else None}
