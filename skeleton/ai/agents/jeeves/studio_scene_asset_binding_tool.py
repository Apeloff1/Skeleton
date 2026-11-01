"""Typed read-only Jeeves original scene asset binding adapter."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_asset_bindings import (
    compile_scene_asset_bindings,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_scene_asset_binding_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_scene_asset_binding_result.v1"
_FIELDS = frozenset({"schema", "project_id", "expected_source_digest",
                     "expected_visual_digest", "expected_session_digest",
                     "actions", "assignments"})


def scene_asset_binding_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_authored_scene_asset_bindings",
        "description": "Source-bound original scene asset recipe work orders; no asset generation claim",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_visual_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64},
                "assignments": {"type": "object"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "expected_visual_digest", "actions", "assignments"],
        },
    }


def execute_scene_asset_binding_tool(request: Mapping[str, Any], *,
                                     authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves asset binding requires operator authorization")
    if type(request) is not dict or not set(request).issubset(_FIELDS):
        raise StudioQuestError("invalid original asset binding tool fields")
    if request.get("schema") != REQUEST_SCHEMA:
        raise StudioQuestError("invalid original asset binding tool schema")
    project = request.get("project_id")
    if type(project) is not str or not 1 <= len(project) <= 128:
        raise StudioQuestError("invalid original asset binding project")
    if type(request.get("actions")) is not list:
        raise StudioQuestError("invalid original asset binding actions")
    try:
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid original asset binding request") from exc
    if len(raw) > 64 * 1024:
        raise StudioQuestError("asset binding request exceeds byte budget")
    detail = compile_scene_asset_bindings(
        read_blueprint(project), request["actions"], request.get("assignments"),
        authorized=True, expected_source_digest=request.get("expected_source_digest"),
        expected_visual_digest=request.get("expected_visual_digest"),
        expected_session_digest=request.get("expected_session_digest"))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": sha256(raw).hexdigest(), "detail": detail,
        "file_write_performed": False, "native_asset_verified": False,
        "rights_verified": False, "release_certified": False,
    }
    result["result_digest"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    return result
