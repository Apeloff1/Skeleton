"""Jeeves typed, explicit-authoring adapter for structural quest edits."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_quest_structural_edit import compile_quest_structural_edit

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_structural_edit_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_structural_edit_result.v1"
_FIELDS = frozenset({
    "schema", "baseline_compilation", "expected_baseline_digest", "edits",
})


def quest_structural_edit_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_quest_structural_edit",
        "description": "Apply an explicit CAS-leased atomic batch of typed original quest stage and ending edits; recompile the complete sandbox quest.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "baseline_compilation": {"type": "object"},
                "expected_baseline_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "edits": {"type": "array", "minItems": 1, "maxItems": 32,
                          "items": {"type": "object"}},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_quest_structural_edit_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves structural quest authoring requires authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves structural quest edit request")
    _lease(request["expected_baseline_digest"], "Jeeves structural quest baseline")
    detail = compile_quest_structural_edit(
        request["baseline_compilation"], request["edits"],
        authorized=True, expected_baseline_digest=request["expected_baseline_digest"])
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
