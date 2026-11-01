"""Typed read-only Jeeves handoff for canonical offline playable previews."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
    compile_director_handoff,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_director_handoff_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_director_handoff_result.v1"
_FIELDS = frozenset({"schema", "project_id", "expected_source_digest",
                     "expected_visual_digest", "expected_session_digest",
                     "actions", "schedule", "assignments"})


def director_handoff_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_director_handoff",
        "description": "Verified offline HTML5 gameplay handoff plus scene and asset authoring receipts",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_visual_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64},
                "schedule": {"type": "object"},
                "assignments": {"type": "object"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "expected_visual_digest", "actions", "schedule", "assignments"],
        },
    }


def execute_director_handoff_tool(request: Mapping[str, Any], *,
                                  authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves director handoff requires operator authorization")
    if type(request) is not dict or not set(request).issubset(_FIELDS):
        raise StudioQuestError("invalid Jeeves director handoff fields")
    if request.get("schema") != REQUEST_SCHEMA:
        raise StudioQuestError("invalid Jeeves director handoff schema")
    project = request.get("project_id")
    if type(project) is not str or not 1 <= len(project) <= 128:
        raise StudioQuestError("invalid Jeeves director project")
    if type(request.get("actions")) is not list:
        raise StudioQuestError("invalid Jeeves director actions")
    try:
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid director request JSON") from exc
    if len(raw) > 64 * 1024:
        raise StudioQuestError("director request exceeds byte budget")
    manifest, _archive = compile_director_handoff(
        read_blueprint(project), request["actions"],
        request.get("schedule"), request.get("assignments"),
        authorized=True, expected_source_digest=request.get("expected_source_digest"),
        expected_visual_digest=request.get("expected_visual_digest"),
        expected_session_digest=request.get("expected_session_digest"))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": sha256(raw).hexdigest(),
        "detail": manifest, "file_write_performed": False,
        "native_scene_timing_verified": False,
        "native_asset_binding_verified": False,
        "release_certified": False,
    }
    result["result_digest"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    return result
