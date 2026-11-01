"""Static, typed Jeeves adapter for bounded authored ending witness search."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_quest_ending_witness import compile_ending_witness

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_ending_witness_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_ending_witness_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "target_ending", "initial_actions",
    "max_states", "max_depth", "expected_source_digest",
    "expected_initial_session_digest",
})


def quest_ending_witness_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_quest_ending_witness",
        "description": "Search canonical authored quest alternatives for a replayable ending witness; budget exhaustion is inconclusive.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "target_ending": {"type": "string", "minLength": 1, "maxLength": 256},
                "initial_actions": {"type": "array", "maxItems": 64},
                "max_states": {"type": "integer", "minimum": 1, "maximum": 2048},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 64},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_initial_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_quest_ending_witness_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves ending witness requires authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves ending witness request")
    _lease(request["expected_source_digest"], "ending witness source")
    _lease(request["expected_initial_session_digest"], "ending witness session")
    detail = compile_ending_witness(
        read_blueprint(request["project_id"]),
        target_ending=request["target_ending"],
        initial_actions=request["initial_actions"],
        max_states=request["max_states"], max_depth=request["max_depth"],
        authorized=True, expected_source_digest=request["expected_source_digest"],
        expected_initial_session_digest=request["expected_initial_session_digest"])
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
