"""Typed read-only Jeeves adapter for original-world NPC transit constraints."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_npc_transit import (
    PROMPT, compile_npc_transit, propose_npc_transit, compile_transit_playable,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_transit_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_transit_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "temporal_receipt", "prompt", "graph", "playable_manifest"}


def npc_transit_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_npc_transit",
        "description": "Source-replayed NPC travel estimates and playable conflict gate",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "temporal_receipt": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "graph": {"type": "object"},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "temporal_receipt"],
        },
    }


def execute_npc_transit_tool(request: Mapping[str, Any], *,
                             authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC transit requires authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("graph" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("temporal_receipt")) is not dict
            or request["temporal_receipt"].get("source_digest") !=
               request.get("expected_source_digest")
            or len(_canonical(request)) > 262144):
        raise StudioQuestError("invalid Jeeves NPC transit request")
    docs = read_blueprint(request["project_id"])
    detail = (propose_npc_transit(
        docs, request["temporal_receipt"], request["prompt"], authorized=True)
        if "prompt" in request else compile_npc_transit(
            docs, request["temporal_receipt"], request["graph"], authorized=True))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if "playable_manifest" in request:
        if type(request["playable_manifest"]) is not bool:
            raise StudioQuestError("playable manifest flag must be boolean")
        if request["playable_manifest"]:
            result["playable_handoff"] = compile_transit_playable(
                docs, detail, authorized=True)
    result["result_digest"] = _digest(result)
    return result
