"""Typed Jeeves adapter for collision/health-verified playable waypoint handoff."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)
from skeleton.ai.game_builder.studio_waypoint_handoff import compile_waypoint_handoff

REQUEST_SCHEMA = "skeleton.jeeves.studio_waypoint_handoff_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_waypoint_handoff_result.v1"


def waypoint_handoff_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_waypoint_handoff",
        "description": (
            "Read-only proposal for authoritative walk and hazard replay; "
            "returns a source-bound playable save without choosing quest outcomes"
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "session_receipt": {"type": "object"},
                "waypoints": {"type": "array", "maxItems": 8},
                "max_hazard_contacts": {"type": "integer", "minimum": 0, "maximum": 16},
            },
            "required": [
                "schema", "project_id", "expected_source_digest",
                "expected_session_digest", "session_receipt",
                "waypoints", "max_hazard_contacts",
            ],
        },
    }


def execute_waypoint_handoff_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves playable handoff requires authorization")
    if (type(request) is not dict or set(request) != {
            "schema", "project_id", "expected_source_digest",
            "expected_session_digest", "session_receipt", "waypoints",
            "max_hazard_contacts",
        } or request["schema"] != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or type(request["session_receipt"]) is not dict
            or len(_canonical(request)) > 32768):
        raise StudioQuestError("invalid typed Jeeves waypoint handoff request")
    _lease(request["expected_source_digest"], "Jeeves handoff source")
    _lease(request["expected_session_digest"], "Jeeves handoff session")
    detail = compile_waypoint_handoff(
        read_blueprint(request["project_id"]), request["session_receipt"],
        waypoints=request["waypoints"],
        max_hazard_contacts=request["max_hazard_contacts"],
        authorized=True, expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request["expected_session_digest"],
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "source_replay_verified": True,
        "file_write_performed": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
