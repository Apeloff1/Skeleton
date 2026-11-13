"""Transactional weather timeline and hazard editor with gameplay replay preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_weather import (
    MAX_BOARD_BYTES, build_weather_game, validate_weather, verify_weather_game,
)

SCHEMA = "skeleton.game.harbor.weather-edit.v1"
MAX_REVISION_BYTES = 196608
FIELDS = {
    "schema", "source", "before", "before_digest", "edits", "after",
    "after_digest", "preview", "revision_digest",
}


def edit_weather(source: Any, board: Any, edits: Any, *,
                 expected_source_digest: str, expected_board_digest: str,
                 preview_report: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    before = validate_weather(board, world)
    if expected_source_digest != digest(world) or expected_board_digest != digest(before):
        raise HarborError("stale weather authoring lease")
    if (not isinstance(edits, list) or not 1 <= len(edits) <= 16
            or len(canonical(edits)) > MAX_BOARD_BYTES):
        raise HarborError("invalid weather edits")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"target", "id", "field", "value"}, "weather edit")
        target = edit["target"]
        field = edit["field"]
        if type(target) is not str or type(field) is not str:
            raise HarborError("invalid weather edit selector")
        if target == "settings" and edit["id"] == "settings" and field in ("max_energy", "rest_gain"):
            after[field] = deepcopy(edit["value"])
        elif target == "phase" and field in ("tick", "kind"):
            index = edit["id"]
            if type(index) is not int or not 0 <= index < len(after["phases"]):
                raise HarborError("invalid weather phase index")
            after["phases"][index][field] = deepcopy(edit["value"])
        elif target == "hazard" and field in ("at", "energy_cost"):
            name = _identifier(edit["id"], "weather edit hazard")
            hazard = next((h for h in after["hazards"] if h["id"] == name), None)
            if hazard is None:
                raise HarborError("unknown weather hazard")
            hazard[field] = deepcopy(edit["value"])
        else:
            raise HarborError("unsupported weather edit")
    after = validate_weather(after, world)
    preview = None
    if preview_report is not None:
        verify_weather_game(preview_report)
        if (preview_report["source_digest"] != digest(world)
                or preview_report["board"] != before):
            raise HarborError("weather preview source mismatch")
        actions = [event["action"] for event in preview_report["bundle"]["events"]]
        replay = build_weather_game(world, after, actions)
        preview = {
            "report": deepcopy(preview_report),
            "before_energy": preview_report["energy"],
            "after_energy": replay["energy"],
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
        raise HarborError("weather revision exceeds byte limit")
    return revision


def verify_weather_edit(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "weather revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized weather revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("weather revision digest mismatch")
    preview = revision["preview"]
    if preview is not None:
        _keys(preview, {"report", "before_energy", "after_energy", "before_digest",
                        "after_digest"}, "weather revision preview")
    rebuilt = edit_weather(
        revision["source"], revision["before"], revision["edits"],
        expected_source_digest=digest(revision["source"]),
        expected_board_digest=revision["before_digest"],
        preview_report=preview["report"] if preview is not None else None,
    )
    if rebuilt != revision:
        raise HarborError("weather authoring replay mismatch")
    return {"board_digest": rebuilt["after_digest"],
            "hazards": len(rebuilt["after"]["hazards"]),
            "preview_energy": preview["after_energy"] if preview is not None else None}
