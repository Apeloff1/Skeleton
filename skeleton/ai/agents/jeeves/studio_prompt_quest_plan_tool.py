"""Typed Jeeves original quest authoring adapter (no model invocation)."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_prompt_quest_plan import compile_prompt_quest_plan

REQUEST_SCHEMA = "skeleton.jeeves.studio_prompt_quest_plan_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_prompt_quest_plan_result.v1"


def prompt_quest_plan_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_prompt_quest_plan",
        "description": "Compile an operator-attested original typed quest plan from a prompt into replayable canonical quest source.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "plan": {"type": "object"},
                "expected_plan_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": ["schema", "plan", "expected_plan_digest"],
        },
    }


def execute_prompt_quest_plan_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves original quest authoring requires authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "plan", "expected_plan_digest"}
            or request.get("schema") != REQUEST_SCHEMA
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid typed Jeeves original quest request")
    _lease(request["expected_plan_digest"], "Jeeves original quest plan")
    detail = compile_prompt_quest_plan(
        request["plan"], authorized=True,
        expected_plan_digest=request["expected_plan_digest"])
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
