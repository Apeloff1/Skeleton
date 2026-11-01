"""Static Jeeves adapter for source-bound spoiler-safe quest hints."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_quest_hint_deck import (
    PROMPT, compile_quest_hint_deck, propose_quest_hint_deck,
    compile_quest_hint_playable,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_hint_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_hint_result.v1"
_FIELDS = {"schema", "project_id", "expected_source_digest",
           "actions", "prompt", "authoring", "playable_manifest"}


def quest_hint_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_quest_hints",
        "description": "Source-replayed spoiler-safe quest hints for available or completed stages",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "prompt": {"type": "string", "const": PROMPT},
                "authoring": {"type": "object"},
                "playable_manifest": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_quest_hint_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves quest hints require authorization")
    if (type(request) is not dict or set(request) - _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or ("prompt" in request) == ("authoring" in request)
            or type(request.get("project_id")) is not str
            or type(request.get("actions")) is not list
            or len(_canonical(request)) > 49152):
        raise StudioQuestError("invalid Jeeves quest hint request")
    if "playable_manifest" in request and type(request["playable_manifest"]) is not bool:
        raise StudioQuestError("invalid quest hint playable flag")
    docs = read_blueprint(request["project_id"])
    kwargs = {"authorized": True,
              "expected_source_digest": request["expected_source_digest"]}
    detail = (propose_quest_hint_deck(
        docs, request["actions"], request["prompt"], **kwargs)
        if "prompt" in request else compile_quest_hint_deck(
            docs, request["actions"], request["authoring"], **kwargs))
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    if request.get("playable_manifest", False):
        result["playable_handoff"] = compile_quest_hint_playable(
            docs, detail, authorized=True)
    result["result_digest"] = _digest(result)
    return result
