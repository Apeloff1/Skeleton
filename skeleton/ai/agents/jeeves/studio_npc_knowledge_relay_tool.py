"""Static Jeeves adapter for source-replayed authored NPC knowledge relays."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_relay import (
    PROMPT, compile_npc_knowledge_relay, propose_npc_knowledge_relay,
    compile_npc_relay_playable,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_knowledge_relay_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_knowledge_relay_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "exchange_receipt", "prompt", "authoring", "playable_manifest"}


def npc_knowledge_relay_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_npc_knowledge_relay",
        "description": "Replay authored multi-hop NPC knowledge against source, time and meeting proof",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "exchange_receipt": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "authoring": {"type": "object"},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "exchange_receipt"],
        },
    }


def execute_npc_knowledge_relay_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC relay requires operator authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("authoring" in request)
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or type(request.get("exchange_receipt")) is not dict
            or request["exchange_receipt"].get("source_digest")
               != request.get("expected_source_digest")
            or len(_canonical(request)) > 524288):
        raise StudioQuestError("invalid typed Jeeves NPC relay request")
    if ("playable_manifest" in request
            and type(request["playable_manifest"]) is not bool):
        raise StudioQuestError("invalid NPC relay playable flag")
    docs = read_blueprint(request["project_id"])
    kwargs = {"authorized": True,
              "expected_source_digest": request["expected_source_digest"]}
    detail = (propose_npc_knowledge_relay(
        docs, request["exchange_receipt"], request["prompt"], **kwargs)
        if "prompt" in request else compile_npc_knowledge_relay(
            docs, request["exchange_receipt"], request["authoring"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if request.get("playable_manifest", False):
        result["playable_handoff"] = compile_npc_relay_playable(
            docs, detail, authorized=True)
    result["result_digest"] = _digest(result)
    return result
