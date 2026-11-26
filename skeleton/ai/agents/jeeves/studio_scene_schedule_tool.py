"""Reviewed typed Jeeves adapter for deterministic scene schedule rehearsal."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import compile_scene_schedule

REQUEST_SCHEMA = "skeleton.jeeves.studio_scene_schedule_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_scene_schedule_result.v1"
_ALLOWED = frozenset({"schema", "project_id", "expected_source_digest",
                      "expected_session_digest", "actions", "schedule"})


def scene_schedule_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_authored_scene_schedule",
        "description": "Replay-verified original NPC scene schedule; no native time or write claim",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64},
                "schedule": {"type": "object", "additionalProperties": False,
                             "required": ["scene_ticks", "npc_turnaround_ticks", "min_start_ticks"],
                             "properties": {
                                 "scene_ticks": {"type": "object"},
                                 "npc_turnaround_ticks": {"type": "integer", "minimum": 0},
                                 "min_start_ticks": {"type": "object"},
                             }},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "actions", "schedule"],
        },
    }


def execute_scene_schedule_tool(request: Mapping[str, Any], *,
                                authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves schedule requires operator authorization")
    if type(request) is not dict or set(request) != _ALLOWED.intersection(request):
        raise StudioQuestError("invalid typed scene schedule fields")
    if request.get("schema") != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported scene schedule request schema")
    project = request.get("project_id")
    if type(project) is not str or not 1 <= len(project) <= 128:
        raise StudioQuestError("invalid scene schedule project")
    actions = request.get("actions")
    if type(actions) is not list:
        raise StudioQuestError("invalid scene schedule actions")
    try:
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid scene schedule request JSON") from exc
    if len(raw) > 32 * 1024:
        raise StudioQuestError("scene schedule request exceeds budget")
    detail = compile_scene_schedule(
        read_blueprint(project), actions, request.get("schedule"),
        authorized=True, expected_source_digest=request.get("expected_source_digest"),
        expected_session_digest=request.get("expected_session_digest"))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": sha256(raw).hexdigest(), "detail": detail,
        "file_write_performed": False, "replay_verified": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    result["result_digest"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()
    return result
