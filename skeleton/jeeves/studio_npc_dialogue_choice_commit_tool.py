"""Explicit-authoring Jeeves adapter for replay-verified NPC quest choice."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)
from skeleton.ai.game_builder.studio_npc_dialogue_choice_commit import (
    compile_npc_dialogue_choice_commit,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_dialogue_choice_commit_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_dialogue_choice_commit_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "contact_receipt", "alternative",
    "expected_contact_digest", "expected_source_digest",
    "expected_walk_digest", "expected_quest_digest",
})


def npc_dialogue_choice_commit_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_npc_dialogue_choice_commit",
        "description": (
            "Replay one authored quest alternative from source-bound playable "
            "NPC contact; requires explicit operator authoring permission. "
            "Returns a deterministic choice receipt, not native dialogue proof."
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "contact_receipt": {"type": "object"},
                "alternative": {"type": "string", "minLength": 1, "maxLength": 256},
                "expected_contact_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_walk_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_quest_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_npc_dialogue_choice_commit_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC dialogue choice requires authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or type(request["contact_receipt"]) is not dict
            or len(_canonical(request)) > 512 * 1024):
        raise StudioQuestError("invalid typed Jeeves NPC dialogue choice request")
    for key in ("expected_contact_digest", "expected_source_digest",
                "expected_walk_digest", "expected_quest_digest"):
        _lease(request[key], "Jeeves NPC dialogue choice " + key)
    detail = compile_npc_dialogue_choice_commit(
        read_blueprint(request["project_id"]), request["contact_receipt"],
        alternative=request["alternative"], authorized=True,
        expected_contact_digest=request["expected_contact_digest"],
        expected_source_digest=request["expected_source_digest"],
        expected_walk_digest=request["expected_walk_digest"],
        expected_quest_digest=request["expected_quest_digest"],
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
