"""Read-only typed Jeeves tool for independent authored ending witnesses."""
from __future__ import annotations
from typing import Any, Mapping
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_quest_ending_coverage import compile_ending_coverage

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_ending_coverage_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_ending_coverage_result.v1"
FIELDS = frozenset({"schema", "project_id", "authoring",
                    "expected_source_digest", "expected_initial_session_digest"})


def quest_ending_coverage_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_quest_ending_coverage",
        "description": "Prove independent authored quest ending witnesses with canonical source replay.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "authoring": {"type": "object"},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_initial_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            }, "required": sorted(FIELDS),
        },
    }


def execute_quest_ending_coverage_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves ending coverage requires authorization")
    if (type(request) is not dict or set(request) != FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves ending coverage request")
    report = compile_ending_coverage(
        read_blueprint(request["project_id"]), request["authoring"],
        authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_initial_session_digest=request["expected_initial_session_digest"])
    payload = {"schema": RESULT_SCHEMA, "request_digest": _digest(request),
               "detail": report, "file_write_performed": False,
               "release_certified": False}
    payload["result_digest"] = _digest(payload)
    return payload
