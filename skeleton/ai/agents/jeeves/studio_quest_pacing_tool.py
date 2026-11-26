"""Typed, permission-bound Jeeves quest pacing proposal adapter."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_quest_pacing import PROMPT, propose_quest_pacing

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_pacing_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_pacing_result.v1"
FIELDS = frozenset({
    "schema", "project_id", "actions", "target_ending",
    "expected_source_digest", "expected_initial_session_digest",
})


def quest_pacing_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_quest_pacing",
        "description": "Draft editable, unmeasured quest pacing estimates from canonical source.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "actions": {"type": "array", "maxItems": 64},
                "target_ending": {"type": "string", "minLength": 1, "maxLength": 256},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_initial_session_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": sorted(FIELDS),
        },
    }


def execute_quest_pacing_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves pacing proposal requires authorization")
    if (type(request) is not dict or set(request) != FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves pacing request")
    plan = propose_quest_pacing(
        read_blueprint(request["project_id"]), PROMPT, request["actions"],
        target_ending=request["target_ending"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_initial_session_digest=request["expected_initial_session_digest"])
    result = {"schema": RESULT_SCHEMA, "request_digest": _digest(request),
              "detail": plan, "file_write_performed": False,
              "release_certified": False}
    result["result_digest"] = _digest(result)
    return result
