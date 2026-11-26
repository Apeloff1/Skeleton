"""Typed read-only Jeeves hazard-aware route preview."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_waypoint_risk import compile_waypoint_risk

REQUEST_SCHEMA = "skeleton.jeeves.studio_waypoint_risk_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_waypoint_risk_result.v1"


def waypoint_risk_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_waypoint_risk",
        "description": "Read-only source-bound route planning with authored hazard/health budget",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_index": {"type": "integer", "minimum": 0},
                "start": {"type": "array", "minItems": 2, "maxItems": 2},
                "waypoints": {"type": "array", "maxItems": 8},
                "max_hazard_contacts": {"type": "integer", "minimum": 0, "maximum": 16},
            },
            "required": [
                "schema", "project_id", "expected_source_digest",
                "scene_index", "start", "waypoints", "max_hazard_contacts",
            ],
        },
    }


def execute_waypoint_risk_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves risk route requires authorization")
    if (type(request) is not dict or set(request) != {
            "schema", "project_id", "expected_source_digest",
            "scene_index", "start", "waypoints", "max_hazard_contacts",
        } or request["schema"] != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 4096):
        raise StudioQuestError("invalid typed Jeeves risk route request")
    _lease(request["expected_source_digest"], "Jeeves risk source")
    detail = compile_waypoint_risk(
        read_blueprint(request["project_id"]),
        scene_index=request["scene_index"], start=request["start"],
        waypoints=request["waypoints"],
        max_hazard_contacts=request["max_hazard_contacts"],
        authorized=True, expected_source_digest=request["expected_source_digest"],
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "source_replay_verified": True,
        "file_write_performed": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
