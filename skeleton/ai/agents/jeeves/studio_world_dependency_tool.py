"""Reviewed read-only Jeeves tool for source-leased world dependency DAGs."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_world_dependency import (
    SCHEMA, PROMPT, compile_dependency_world_batch, execute_dependency_world_batch,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_world_dependency_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_world_dependency_result.v1"


def world_dependency_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_world_dependency",
        "description": "Compile and source-replay an explicitly authorized read-only world dependency DAG",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "expected_catalog_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "graph": {"type": "object"},
            },
            "required": ["schema", "expected_catalog_digest", "graph"],
        },
    }


def execute_world_dependency_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dependency workflow requires authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "expected_catalog_digest", "graph"}
            or request["schema"] != REQUEST_SCHEMA
            or type(request["graph"]) is not dict
            or len(_canonical(request)) > 48 * 1024):
        raise StudioQuestError("invalid typed Jeeves dependency request")
    _lease(request["expected_catalog_digest"], "Jeeves dependency catalog")
    graph = request["graph"]
    if graph.get("schema") != SCHEMA or graph.get("prompt") != PROMPT:
        raise StudioQuestError("unsupported typed dependency graph prompt")
    proof = compile_dependency_world_batch(
        graph, authorized=True,
        expected_catalog_digest=request["expected_catalog_digest"],
    )
    execution = execute_dependency_world_batch(proof, authorized=True)
    output: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "request_digest": _digest(request),
        "dependency_proof_digest": proof["proof_digest"],
        "detail": execution, "source_replay_verified": True,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(output)) > 1024 * 1024 - 128:
        raise StudioQuestError("Jeeves dependency result exceeds budget")
    output["result_digest"] = _digest(output)
    return output
