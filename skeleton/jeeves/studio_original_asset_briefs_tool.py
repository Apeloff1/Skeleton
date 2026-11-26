"""Typed Jeeves original asset production brief tool."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_original_asset_briefs import (
    PROMPT, compile_original_asset_briefs, propose_original_asset_briefs,
    compile_original_asset_briefs_playable,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_original_asset_briefs_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_original_asset_briefs_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "expected_visual_digest", "actions", "binding_receipt",
           "prompt", "authoring", "playable_manifest"}


def original_asset_briefs_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_asset_briefs",
        "description": "Original source-bound asset design briefs, never fabricated artifact or rights proof",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_visual_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "binding_receipt": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "authoring": {"type": "object"},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "expected_visual_digest", "actions", "binding_receipt"],
        },
    }


def execute_original_asset_briefs_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves original asset briefs require authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("authoring" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("actions")) is not list
            or type(request.get("binding_receipt")) is not dict
            or len(_canonical(request)) > 128 * 1024):
        raise StudioQuestError("invalid Jeeves original asset brief request")
    if "playable_manifest" in request and type(request["playable_manifest"]) is not bool:
        raise StudioQuestError("invalid original asset playable flag")
    docs = read_blueprint(request["project_id"])
    kwargs = {
        "authorized": True,
        "expected_source_digest": request["expected_source_digest"],
        "expected_visual_digest": request["expected_visual_digest"],
    }
    detail = (propose_original_asset_briefs(
        docs, request["actions"], request["binding_receipt"],
        request["prompt"], **kwargs) if "prompt" in request else
        compile_original_asset_briefs(
            docs, request["actions"], request["binding_receipt"],
            request["authoring"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if request.get("playable_manifest", False):
        result["playable_handoff"] = compile_original_asset_briefs_playable(
            docs, detail, authorized=True)
    result["result_digest"] = _digest(result)
    return result
