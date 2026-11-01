"""Explicit read-only Jeeves adapter for dependency edit impact previews."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_world_dependency_impact import compile_dependency_impact

REQUEST_SCHEMA = "skeleton.jeeves.studio_world_dependency_impact_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_world_dependency_impact_result.v1"


def world_dependency_impact_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_world_dependency_impact",
        "description": "Read-only source-replayed impact of an original-world dependency edit",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "expected_catalog_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "baseline_proof": {"type": "object"},
                "candidate_graph": {"type": "object"},
            },
            "required": ["schema", "expected_catalog_digest", "baseline_proof", "candidate_graph"],
        },
    }


def execute_world_dependency_impact_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dependency impact requires authorization")
    if (
        type(request) is not dict
        or set(request) != {"schema", "expected_catalog_digest", "baseline_proof", "candidate_graph"}
        or request["schema"] != REQUEST_SCHEMA
        or type(request["baseline_proof"]) is not dict
        or type(request["candidate_graph"]) is not dict
        or len(_canonical(request)) > 512 * 1024
    ):
        raise StudioQuestError("invalid typed Jeeves dependency impact request")
    _lease(request["expected_catalog_digest"], "Jeeves dependency impact catalog")
    detail = compile_dependency_impact(
        request["baseline_proof"], request["candidate_graph"],
        authorized=True, expected_catalog_digest=request["expected_catalog_digest"],
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "detail": detail, "source_replay_verified": True,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > 1024 * 1024 - 128:
        raise StudioQuestError("Jeeves dependency impact result exceeds budget")
    result["result_digest"] = _digest(result)
    return result
