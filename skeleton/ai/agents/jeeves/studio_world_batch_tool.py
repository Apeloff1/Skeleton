"""Static Jeeves adapter for bounded read-only world workflow execution."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_world_batch import (
    PROMPT, propose_world_batch_plan, execute_world_batch,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_world_batch_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_world_batch_result.v1"


def world_batch_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_world_batch",
        "description": "Bounded deterministic read-only execution of vetted typed Jeeves world tools",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "expected_catalog_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "prompt": {"type": "string", "const": PROMPT},
                "requests": {"type": "array", "minItems": 1, "maxItems": 8},
            },
            "required": ["schema", "expected_catalog_digest", "prompt", "requests"],
        },
    }


def execute_world_batch_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves world batch requires authorization")
    if (type(request) is not dict or set(request) != {
            "schema", "expected_catalog_digest", "prompt", "requests"}
            or request["schema"] != REQUEST_SCHEMA
            or len(_canonical(request)) > 48 * 1024):
        raise StudioQuestError("invalid Jeeves world batch request")
    plan = propose_world_batch_plan(
        request["prompt"], request["requests"], authorized=True,
        expected_catalog_digest=request["expected_catalog_digest"])
    detail = execute_world_batch(plan, authorized=True)
    result = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "plan_digest": plan["plan_digest"], "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
