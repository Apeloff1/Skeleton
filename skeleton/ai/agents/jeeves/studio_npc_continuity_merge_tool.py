"""Operator-authorized typed Jeeves continuity branch reconciliation tool."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_merge import (
    PROMPT, compile_npc_continuity_merge, propose_npc_continuity_merge,
    compile_npc_continuity_merge_playable,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_continuity_merge_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_continuity_merge_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "baseline_receipt", "candidate_receipt", "prompt",
           "authoring", "playable_manifest"}


def npc_continuity_merge_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_npc_continuity_merge",
        "description": "Reconcile two source-verified NPC annotation branches; never rewrite events",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "baseline_receipt": {"type": "object"},
                "candidate_receipt": {"type": "object"},
                "prompt": {"type": "string", "const": PROMPT},
                "authoring": {"type": "object"},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "baseline_receipt", "candidate_receipt"],
        },
    }


def execute_npc_continuity_merge_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves continuity merge requires authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("authoring" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("baseline_receipt")) is not dict
            or type(request.get("candidate_receipt")) is not dict
            or len(_canonical(request)) > 1024 * 1024):
        raise StudioQuestError("invalid Jeeves continuity merge request")
    if "playable_manifest" in request and type(request["playable_manifest"]) is not bool:
        raise StudioQuestError("invalid continuity merge playable flag")
    docs = read_blueprint(request["project_id"])
    kwargs = {"authorized": True,
              "expected_source_digest": request["expected_source_digest"]}
    detail = (propose_npc_continuity_merge(
        docs, request["baseline_receipt"], request["candidate_receipt"],
        request["prompt"], **kwargs) if "prompt" in request else
        compile_npc_continuity_merge(
            docs, request["baseline_receipt"], request["candidate_receipt"],
            request["authoring"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if request.get("playable_manifest", False):
        result["playable_handoff"] = compile_npc_continuity_merge_playable(
            docs, detail, authorized=True)
    result["result_digest"] = _digest(result)
    return result
