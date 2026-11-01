"""Typed read-only Jeeves tool for source-bound scene timing comparison."""
from __future__ import annotations
from typing import Any, Mapping
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_rehearsal import (
    _canonical, _digest, compile_scene_rehearsal,
)
REQUEST_SCHEMA = "skeleton.jeeves.studio_scene_rehearsal_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_scene_rehearsal_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "expected_session_digest", "actions", "baseline_schedule",
           "candidate_schedule"}
_REQUIRED = _FIELDS - {"expected_session_digest"}


def scene_rehearsal_tool_schema() -> dict[str, object]:
    schedule = {"type": "object", "additionalProperties": False,
                "required": ["scene_ticks", "npc_turnaround_ticks", "min_start_ticks"],
                "properties": {"scene_ticks": {"type": "object"},
                               "npc_turnaround_ticks": {"type": "integer", "minimum": 0},
                               "min_start_ticks": {"type": "object"}}}
    return {"name": "studio_original_scene_rehearsal",
            "description": "Compare source-replayed NPC/quest scene critical paths",
            "parameters": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "schema": {"type": "string", "const": REQUEST_SCHEMA},
                    "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                    "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "actions": {"type": "array", "maxItems": 64},
                    "baseline_schedule": schedule, "candidate_schedule": schedule},
                "required": sorted(_REQUIRED)}}


def execute_scene_rehearsal_tool(request: Mapping[str, Any], *,
                                 authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves scene rehearsal requires authorization")
    if (type(request) is not dict or not _REQUIRED.issubset(request)
            or not set(request).issubset(_FIELDS)
            or request.get("schema") != REQUEST_SCHEMA):
        raise StudioQuestError("invalid Jeeves scene rehearsal fields")
    project = request["project_id"]
    if type(project) is not str or not 1 <= len(project) <= 128:
        raise StudioQuestError("invalid rehearsal project")
    if type(request["actions"]) is not list:
        raise StudioQuestError("invalid rehearsal actions")
    if len(_canonical(request)) > 32768:
        raise StudioQuestError("Jeeves rehearsal exceeds request budget")
    detail = compile_scene_rehearsal(
        read_blueprint(project), request["actions"], request["baseline_schedule"],
        request["candidate_schedule"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request.get("expected_session_digest"))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "native_timing_verified": False, "release_certified": False}
    result["result_digest"] = _digest(result)
    return result
