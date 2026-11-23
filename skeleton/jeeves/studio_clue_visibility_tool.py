"""Typed, read-only Jeeves clue visibility planning and replay adapter."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_clue_visibility import (
    compile_clue_visibility, propose_clue_visibility,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest

REQUEST_SCHEMA = "skeleton.jeeves.studio_clue_visibility_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_clue_visibility_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "expected_session_digest", "actions", "authoring", "prompt"}


def clue_visibility_tool_schema() -> dict[str, object]:
    return {"name": "studio_original_clue_visibility",
            "description": "Source-replayed spoiler-safe clue trail for authored scenes",
            "parameters": {"type": "object", "additionalProperties": False,
                           "properties": {
                               "schema": {"type": "string", "const": REQUEST_SCHEMA},
                               "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                               "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                               "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                               "actions": {"type": "array", "maxItems": 64},
                               "authoring": {"type": "object"},
                               "prompt": {"type": "string", "minLength": 1, "maxLength": 512}},
                           "required": ["schema", "project_id", "expected_source_digest", "actions"]}}


def execute_clue_visibility_tool(request: Mapping[str, Any], *,
                                 authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves clue visibility requires authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("authoring" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("actions")) is not list):
        raise StudioQuestError("invalid Jeeves clue visibility request")
    if len(_canonical(request)) > 65536:
        raise StudioQuestError("Jeeves clue request exceeds byte budget")
    docs = read_blueprint(request["project_id"])
    args = (docs, request["actions"], request.get("prompt", request.get("authoring")))
    kwargs = {"authorized": True,
              "expected_source_digest": request.get("expected_source_digest"),
              "expected_session_digest": request.get("expected_session_digest")}
    detail = (propose_clue_visibility(*args, **kwargs)
              if "prompt" in request else compile_clue_visibility(*args, **kwargs))
    result = {"schema": RESULT_SCHEMA, "project_id": request["project_id"],
              "request_digest": _digest(request), "detail": detail,
              "file_write_performed": False, "source_replay_verified": True,
              "release_certified": False}
    result["result_digest"] = _digest(result)
    return result
