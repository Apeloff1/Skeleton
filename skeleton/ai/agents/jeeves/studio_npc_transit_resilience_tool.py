"""Static typed Jeeves route disruption adapter; no inferred authority."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience import (
    PROMPT, compile_npc_transit_resilience, propose_npc_transit_resilience,
    select_npc_transit_fallback,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_transit_resilience_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_transit_resilience_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest", "baseline_receipt",
           "prompt", "variants", "select", "playable_manifest"}


def npc_transit_resilience_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_npc_transit_resilience",
        "description": "Source-leased directed-route outage proof with fail-closed playable selection",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "baseline_receipt": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "variants": {"type": "array", "maxItems": 12},
                "select": {"type": "string", "minLength": 1, "maxLength": 48},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "baseline_receipt"],
        },
    }


def execute_npc_transit_resilience_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC resilience requires authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("variants" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("baseline_receipt")) is not dict
            or request["baseline_receipt"].get("source_digest") !=
               request.get("expected_source_digest")
            or len(_canonical(request)) > 262144):
        raise StudioQuestError("invalid Jeeves NPC resilience request")
    if "playable_manifest" in request and type(request["playable_manifest"]) is not bool:
        raise StudioQuestError("invalid NPC resilience playable flag")
    if request.get("playable_manifest", False) and "select" not in request:
        raise StudioQuestError("NPC resilience playable handoff requires selection")
    docs = read_blueprint(request["project_id"])
    kwargs = {"authorized": True,
              "expected_source_digest": request["expected_source_digest"]}
    detail = (propose_npc_transit_resilience(
        docs, request["baseline_receipt"], request["prompt"], **kwargs)
        if "prompt" in request else compile_npc_transit_resilience(
            docs, request["baseline_receipt"], request["variants"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if "select" in request:
        result["selection"] = select_npc_transit_fallback(
            docs, detail, request["select"], authorized=True,
            playable=request.get("playable_manifest", False))
    result["result_digest"] = _digest(result)
    return result
