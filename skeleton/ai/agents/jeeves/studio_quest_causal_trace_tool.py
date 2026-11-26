"""Typed, read-only Jeeves adapter for source-verified quest causal witnesses."""
from __future__ import annotations
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_quest_consequence_diff import compile_quest_consequence_diff
from skeleton.ai.game_builder.studio_quest_causal_trace import compile_quest_causal_trace

REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_causal_trace_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_quest_causal_trace_result.v1"
FIELDS = frozenset({"schema", "project_id", "authoring",
                    "expected_source_digest", "expected_initial_session_digest"})


def quest_causal_trace_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_quest_causal_witnesses",
        "description": "Explain original quest endings using canonical authored action witnesses.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "authoring": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "baseline_actions": {"type": "array", "maxItems": 64},
                        "candidate_actions": {"type": "array", "maxItems": 64},
                    },
                    "required": ["baseline_actions", "candidate_actions"],
                },
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_initial_session_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": sorted(FIELDS),
        },
    }


def execute_quest_causal_trace_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves causal witnesses require authorization")
    if (type(request) is not dict or set(request) != FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or type(request["project_id"]) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves causal witness request")
    documents = read_blueprint(request["project_id"])
    consequence = compile_quest_consequence_diff(
        documents, request["authoring"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_initial_session_digest=request["expected_initial_session_digest"],
    )
    trace = compile_quest_causal_trace(documents, consequence, authorized=True)
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": trace, "file_write_performed": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
