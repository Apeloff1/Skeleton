"""Typed read-only Jeeves adapter for canonical browser quest parity."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_story_browser_parity import (
    compile_story_browser_parity,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_story_browser_parity_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_story_browser_parity_result.v1"
FIELDS = frozenset({"schema", "project_id", "actions",
                    "expected_source_digest", "expected_initial_session_digest"})


def story_browser_parity_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_story_browser_parity",
        "description": "Rehearse original authored browser choices against canonical quest endings.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2,
                                      "maxItems": 2,
                                      "items": {"type": "string"}}},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_initial_session_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": sorted(FIELDS),
        },
    }


def execute_story_browser_parity_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves browser parity requires authorization")
    if (type(request) is not dict or set(request) != FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves browser parity request")
    docs = read_blueprint(request["project_id"])
    detail = compile_story_browser_parity(
        docs, request["actions"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_initial_session_digest=request["expected_initial_session_digest"])
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
