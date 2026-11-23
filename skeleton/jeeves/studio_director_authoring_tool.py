"""Typed, permission-gated Jeeves bridge for offline director editor exports.

This adapter does not trust a browser receipt, write files or certify native
assets. It replays the exact canonical source and compiles the playable bundle
through the same director owner used by the operator CLI.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_director_authoring import _parse
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from .studio_director_handoff_tool import (
    REQUEST_SCHEMA as HANDOFF_SCHEMA, execute_director_handoff_tool,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_director_authoring_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_director_authoring_result.v1"
_FIELDS = frozenset({"schema", "project_id", "actions", "export"})
MAX_REQUEST_BYTES = 64 * 1024


def director_authoring_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_director_authoring",
        "description": (
            "Revalidate a source-leased offline editor export and compile an "
            "original playable HTML5 handoff; no file writes or native claims"
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "actions": {"type": "array", "maxItems": 64},
                "export": {"type": "object"},
            },
            "required": ["schema", "project_id", "actions", "export"],
        },
    }


def execute_director_authoring_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves director authoring requires operator authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or type(request.get("actions")) is not list):
        raise StudioQuestError("invalid Jeeves director authoring request")
    encoded = _canonical(request)
    if len(encoded) > MAX_REQUEST_BYTES:
        raise StudioQuestError("Jeeves director authoring request exceeds byte budget")
    export = _parse(_canonical(request["export"]))
    docs = read_blueprint(request["project_id"])
    current_session = replay_quest(docs, request["actions"], authorized=True).digest
    if export["session_digest"] != current_session:
        raise StudioQuestError("stale Jeeves director authoring session lease")
    handoff = execute_director_handoff_tool({
        "schema": HANDOFF_SCHEMA,
        "project_id": request["project_id"],
        "expected_source_digest": export["source_digest"],
        "expected_visual_digest": export["visual_digest"],
        "expected_session_digest": current_session,
        "actions": request["actions"],
        "schedule": export["schedule"],
        "assignments": export["assignments"],
    }, authorized=True)
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "editor_export_source_digest": export["source_digest"],
        "editor_export_session_digest": current_session,
        "detail": handoff["detail"],
        "file_write_performed": False,
        "source_replay_verified": True,
        "native_asset_binding_verified": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
