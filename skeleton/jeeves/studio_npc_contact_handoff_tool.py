"""Typed Jeeves read-only NPC contact eligibility tool."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)
from skeleton.ai.game_builder.studio_npc_contact_handoff import compile_npc_contact_handoff

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_contact_handoff_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_contact_handoff_result.v1"


def npc_contact_handoff_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_npc_contact_handoff",
        "description": (
            "Read-only, source-replayed authored NPC proximity and health proof; "
            "no dialogue generation, conversation mutation or device claims"
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "session_receipt": {"type": "object"},
                "npc_id": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": [
                "schema", "project_id", "expected_source_digest",
                "expected_session_digest", "session_receipt", "npc_id",
            ],
        },
    }


def execute_npc_contact_handoff_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC contact requires authorization")
    if (type(request) is not dict or set(request) != {
            "schema", "project_id", "expected_source_digest",
            "expected_session_digest", "session_receipt", "npc_id",
        } or request["schema"] != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or type(request["session_receipt"]) is not dict
            or len(_canonical(request)) > 32768):
        raise StudioQuestError("invalid typed Jeeves NPC contact request")
    _lease(request["expected_source_digest"], "Jeeves NPC source")
    _lease(request["expected_session_digest"], "Jeeves NPC session")
    detail = compile_npc_contact_handoff(
        read_blueprint(request["project_id"]), request["session_receipt"],
        npc_id=request["npc_id"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request["expected_session_digest"],
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "source_replay_verified": True,
        "file_write_performed": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
