"""Static, read-only Jeeves adapter for authored temporal what-if scenarios."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios import (
    PROMPT, compile_temporal_scenarios, propose_temporal_scenarios,
    select_temporal_scenario,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_temporal_scenarios_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_temporal_scenarios_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "expected_session_digest", "actions", "baseline_authoring",
           "prompt", "candidates", "select", "playable_manifest"}


def temporal_scenarios_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_temporal_scenarios",
        "description": "Compare typed authored scene timing variants against source replay",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64},
                "baseline_authoring": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "candidates": {"type": "array", "maxItems": 12},
                "select": {"type": "string"},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "actions", "baseline_authoring"],
        },
    }


def execute_temporal_scenarios_tool(request: Mapping[str, Any], *,
                                    authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves temporal scenarios require authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("candidates" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("actions")) is not list
            or type(request.get("baseline_authoring")) is not dict
            or len(_canonical(request)) > 65536):
        raise StudioQuestError("invalid Jeeves temporal scenarios request")
    docs = read_blueprint(request["project_id"])
    kwargs = {"authorized": True,
              "expected_source_digest": request.get("expected_source_digest"),
              "expected_session_digest": request.get("expected_session_digest")}
    args = (docs, request["actions"], request["baseline_authoring"])
    detail = (propose_temporal_scenarios(
        *args, request["prompt"], **kwargs) if "prompt" in request else
        compile_temporal_scenarios(*args, request["candidates"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if "select" in request:
        result["selection"] = select_temporal_scenario(
            docs, detail, request["select"], authorized=True,
            playable=request.get("playable_manifest", False))
    elif "playable_manifest" in request:
        raise StudioQuestError("playable manifest requires selected scenario")
    result["result_digest"] = _digest(result)
    return result
