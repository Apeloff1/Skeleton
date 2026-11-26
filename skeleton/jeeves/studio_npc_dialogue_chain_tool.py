"""Typed Jeeves authoring adapter for bounded sequential NPC dialogue."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)
from skeleton.ai.game_builder.studio_npc_dialogue_chain import compile_npc_dialogue_chain

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_dialogue_chain_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_dialogue_chain_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "walk_receipt", "initial_quest_actions", "steps",
    "expected_source_digest", "expected_walk_digest", "expected_quest_digest",
})


def npc_dialogue_chain_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_npc_dialogue_chain",
        "description": (
            "Commit a bounded authored NPC quest choice sequence, verifying "
            "each playable contact against the evolving canonical quest state."
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "walk_receipt": {"type": "object"},
                "initial_quest_actions": {"type": "array", "maxItems": 64},
                "steps": {
                    "type": "array", "minItems": 1, "maxItems": 8,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            key: {"type": "string", "minLength": 1, "maxLength": 256}
                            for key in ("npc_id", "scene_id", "alternative")
                        },
                        "required": ["npc_id", "scene_id", "alternative"],
                    },
                },
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_walk_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_quest_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_npc_dialogue_chain_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC dialogue chain requires authoring authority")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 512 * 1024):
        raise StudioQuestError("invalid typed Jeeves NPC dialogue chain request")
    for key in ("expected_source_digest", "expected_walk_digest",
                "expected_quest_digest"):
        _lease(request[key], "Jeeves NPC dialogue chain " + key)
    detail = compile_npc_dialogue_chain(
        read_blueprint(request["project_id"]), request["walk_receipt"],
        initial_quest_actions=request["initial_quest_actions"],
        steps=request["steps"], authorized=True,
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
