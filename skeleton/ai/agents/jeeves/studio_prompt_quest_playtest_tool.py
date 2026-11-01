"""Read-only typed Jeeves adapter: original plan to playable quest ending."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_prompt_quest_playtest import compile_prompt_quest_playtest

REQUEST_SCHEMA = "skeleton.jeeves.studio_prompt_quest_playtest_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_prompt_quest_playtest_result.v1"
_FIELDS = frozenset({
    "schema", "compilation", "expected_compilation_digest",
    "target_ending", "max_states", "max_depth",
})


def prompt_quest_playtest_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_prompt_quest_playtest",
        "description": "Replay an authored original quest compilation into a bounded canonical ending witness and sandbox playable handoff.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "compilation": {"type": "object"},
                "expected_compilation_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "target_ending": {"type": "string", "minLength": 1, "maxLength": 256},
                "max_states": {"type": "integer", "minimum": 1, "maximum": 2048},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 64},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_prompt_quest_playtest_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves prompt quest playtest requires authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves prompt quest playtest request")
    _lease(request["expected_compilation_digest"], "Jeeves prompt quest compilation")
    detail = compile_prompt_quest_playtest(
        request["compilation"], target_ending=request["target_ending"],
        max_states=request["max_states"], max_depth=request["max_depth"],
        authorized=True,
        expected_compilation_digest=request["expected_compilation_digest"])
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
