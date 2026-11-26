"""Static typed Jeeves adapter for original NPC knowledge provenance."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge import compile_npc_knowledge
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_prompt import propose_npc_knowledge
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_compare import compare_npc_knowledge
from skeleton.ai.game_builder.studio_ecosystem_npc_lineage import compile_npc_lineage
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_knowledge_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_npc_knowledge_result.v1"
_ALLOWED = frozenset({"schema", "project_id", "expected_source_digest",
                      "expected_session_digest", "actions", "prompt", "authoring",
                      "compare_actions", "include_lineage"})


def npc_knowledge_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_npc_knowledge",
        "description": "Original NPC knowledge provenance, prompt planning and replay-gated dialogue handoff",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64},
                "compare_actions": {"type": "array", "maxItems": 64},
                "prompt": {"type": "string", "minLength": 3, "maxLength": 512},
                "authoring": {"type": "object", "additionalProperties": False},
                "include_lineage": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_npc_knowledge_tool(request: Mapping[str, Any], *,
                               authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC knowledge requires operator authorization")
    if (type(request) is not dict or set(request) - _ALLOWED or
            request.get("schema") != REQUEST_SCHEMA):
        raise StudioQuestError("invalid typed Jeeves NPC knowledge request")
    if ("include_lineage" in request and type(request["include_lineage"]) is not bool):
        raise StudioQuestError("invalid NPC knowledge lineage opt-in")
    if ("prompt" in request) == ("authoring" in request):
        raise StudioQuestError("provide exactly one NPC knowledge planning input")
    if type(request.get("project_id")) is not str or type(request.get("actions")) is not list:
        raise StudioQuestError("invalid NPC knowledge project or actions")
    try:
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC knowledge request JSON") from exc
    if len(raw) > 65536:
        raise StudioQuestError("Jeeves NPC knowledge request exceeds budget")
    docs = read_blueprint(request["project_id"])
    kwargs = {
        "authorized": True,
        "expected_source_digest": request.get("expected_source_digest"),
        "expected_session_digest": request.get("expected_session_digest"),
    }
    detail = (propose_npc_knowledge(docs, request["actions"], request["prompt"], **kwargs)
              if "prompt" in request else
              compile_npc_knowledge(docs, request["actions"], request["authoring"], **kwargs))
    authoring = detail["authoring"] if "prompt" in request else request["authoring"]
    if "compare_actions" in request:
        if type(request["compare_actions"]) is not list:
            raise StudioQuestError("invalid NPC knowledge comparison actions")
        detail = {"plan": detail, "comparison": compare_npc_knowledge(
            docs, request["actions"], request["compare_actions"], authoring,
            authorized=True, expected_source_digest=request["expected_source_digest"],
            expected_before_session=request.get("expected_session_digest"))}
    if request.get("include_lineage") is True:
        lineage = compile_npc_lineage(
            docs, request["actions"], authoring, authorized=True,
            expected_source_digest=request["expected_source_digest"],
            expected_session_digest=request.get("expected_session_digest"))
        if "compare_actions" in request:
            detail["lineage"] = lineage
        else:
            detail = {"plan": detail, "lineage": lineage}
    result = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": sha256(raw).hexdigest(), "detail": detail,
        "file_write_performed": False, "replay_verified": True,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    result["result_digest"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    return result
