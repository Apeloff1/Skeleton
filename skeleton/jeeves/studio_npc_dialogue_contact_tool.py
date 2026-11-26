"""Typed read-only Jeeves NPC proximity-gated dialogue preview."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)
from skeleton.ai.game_builder.studio_npc_dialogue_contact import (
    compile_npc_dialogue_contact,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_dialogue_contact_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_dialogue_contact_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_source_digest",
    "expected_walk_digest", "expected_quest_digest", "walk_receipt",
    "npc_id", "scene_id", "quest_actions",
})


def npc_dialogue_contact_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_npc_dialogue_contact",
        "description": (
            "Preview authored NPC choices only when the canonical playable "
            "walk proves proximity and the quest replay proves scene unlock; "
            "no dialogue spoken or choice committed."
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_walk_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_quest_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "walk_receipt": {"type": "object"},
                "npc_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "quest_actions": {"type": "array", "maxItems": 64},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_npc_dialogue_contact_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC dialogue contact requires authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or type(request["walk_receipt"]) is not dict
            or len(_canonical(request)) > 65536):
        raise StudioQuestError("invalid typed Jeeves NPC dialogue request")
    for key in ("expected_source_digest", "expected_walk_digest",
                "expected_quest_digest"):
        _lease(request[key], "Jeeves NPC dialogue " + key)
    detail = compile_npc_dialogue_contact(
        read_blueprint(request["project_id"]), request["walk_receipt"],
        npc_id=request["npc_id"], scene_id=request["scene_id"],
        quest_actions=request["quest_actions"], authorized=True,
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
