"""Typed read-only Jeeves adapter for source-leased temporal constraints."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    compile_temporal_windows, propose_temporal_windows,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_temporal_windows_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_temporal_windows_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "expected_session_digest", "actions", "authoring", "prompt"}


def temporal_windows_tool_schema() -> dict[str, object]:
    return {"name": "studio_original_temporal_windows",
            "description": "Source-replayed authored scene deadlines and occupancy proof",
            "parameters": {"type": "object", "additionalProperties": False,
                           "properties": {
                               "schema": {"type": "string", "const": REQUEST_SCHEMA},
                               "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                               "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                               "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                               "actions": {"type": "array", "maxItems": 64},
                               "authoring": {"type": "object"},
                               "prompt": {"type": "string", "const": "plan source-bound temporal windows"}},
                           "required": ["schema", "project_id", "expected_source_digest", "actions"]}}


def execute_temporal_windows_tool(request: Mapping[str, Any], *,
                                  authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves temporal windows require authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("authoring" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("actions")) is not list
            or len(_canonical(request)) > 65536):
        raise StudioQuestError("invalid Jeeves temporal request")
    docs = read_blueprint(request["project_id"])
    args = (docs, request["actions"], request.get("prompt", request.get("authoring")))
    kwargs = {"authorized": True,
              "expected_source_digest": request.get("expected_source_digest"),
              "expected_session_digest": request.get("expected_session_digest")}
    detail = (propose_temporal_windows(*args, **kwargs)
              if "prompt" in request else compile_temporal_windows(*args, **kwargs))
    result = {"schema": RESULT_SCHEMA, "project_id": request["project_id"],
              "request_digest": _digest(request), "detail": detail,
              "file_write_performed": False, "source_replay_verified": True,
              "release_certified": False}
    result["result_digest"] = _digest(result)
    return result
