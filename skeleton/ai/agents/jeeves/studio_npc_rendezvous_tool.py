"""Static Jeeves adapter for source-leased two-NPC rendezvous planning."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous import (
    PROMPT, compile_npc_rendezvous, propose_npc_rendezvous,
    compile_rendezvous_playable,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_rendezvous_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_rendezvous_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest", "transit_receipt",
           "prompt", "meetings", "playable_manifest"}


def npc_rendezvous_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_npc_rendezvous",
        "description": "Replayed NPC meeting occupancy and directed-travel proof",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "transit_receipt": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "meetings": {"type": "array", "maxItems": 16},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "transit_receipt"],
        },
    }


def execute_npc_rendezvous_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC rendezvous requires authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("meetings" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("transit_receipt")) is not dict
            or request["transit_receipt"].get("source_digest")
               != request.get("expected_source_digest")
            or len(_canonical(request)) > 262144):
        raise StudioQuestError("invalid Jeeves NPC rendezvous request")
    if "playable_manifest" in request and type(request["playable_manifest"]) is not bool:
        raise StudioQuestError("invalid NPC rendezvous playable flag")
    docs = read_blueprint(request["project_id"])
    kwargs = {"authorized": True,
              "expected_source_digest": request["expected_source_digest"]}
    detail = (propose_npc_rendezvous(
        docs, request["transit_receipt"], request["prompt"], **kwargs)
        if "prompt" in request else compile_npc_rendezvous(
            docs, request["transit_receipt"], request["meetings"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if request.get("playable_manifest", False):
        result["playable_handoff"] = compile_rendezvous_playable(
            docs, detail, authorized=True)
    result["result_digest"] = _digest(result)
    return result
