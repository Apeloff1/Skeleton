"""Read-only Jeeves adapter for source-leased quest ending regression review."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_quest_regression_matrix import compile_quest_regression_matrix

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_regression_matrix_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_regression_matrix_result.v1"
_FIELDS = frozenset({
    "schema", "baseline_compilation", "candidate_compilation",
    "expected_baseline_digest", "expected_candidate_digest",
    "max_states", "max_depth",
})


def quest_regression_matrix_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_quest_regression_matrix",
        "description": "Compare source-leased original quest revisions by replaying bounded ending witnesses; uncertainty is explicit.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "baseline_compilation": {"type": "object"},
                "candidate_compilation": {"type": "object"},
                "expected_baseline_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_candidate_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "max_states": {"type": "integer", "minimum": 1, "maximum": 2048},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 64},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_quest_regression_matrix_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves quest regression requires operator authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves quest regression request")
    _lease(request["expected_baseline_digest"], "quest regression baseline")
    _lease(request["expected_candidate_digest"], "quest regression candidate")
    result = compile_quest_regression_matrix(
        request["baseline_compilation"], request["candidate_compilation"],
        authorized=True,
        expected_baseline_digest=request["expected_baseline_digest"],
        expected_candidate_digest=request["expected_candidate_digest"],
        max_states=request["max_states"], max_depth=request["max_depth"],
    )
    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": result, "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload
