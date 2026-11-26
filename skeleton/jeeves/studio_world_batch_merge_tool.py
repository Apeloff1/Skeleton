"""Static Jeeves adapter for source-leased three-way world workflow merging.

No model-provided arguments grant write authority. The tool returns a replayed
typed plan and proof; operator-selected execution and private publication are
separate CLI actions requiring their own authorization and source checks.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_world_batch_merge import merge_world_batch_plans

REQUEST_SCHEMA = "skeleton.jeeves.studio_world_batch_merge_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_world_batch_merge_result.v1"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESULT_BYTES = 64 * 1024


def world_batch_merge_tool_schema() -> dict[str, Any]:
    return {
        "name": "studio_original_world_batch_merge",
        "description": (
            "Fail-closed three-way append-only merge of canonical read-only "
            "Jeeves world workflow plans; does not execute or write"
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "expected_catalog_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$",
                },
                "baseline": {"type": "object"},
                "left": {"type": "object"},
                "right": {"type": "object"},
            },
            "required": [
                "schema", "expected_catalog_digest", "baseline", "left", "right",
            ],
        },
    }


def execute_world_batch_merge_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves world workflow merge requires authorization")
    expected = {
        "schema", "expected_catalog_digest", "baseline", "left", "right",
    }
    if (type(request) is not dict or set(request) != expected
            or request["schema"] != REQUEST_SCHEMA
            or any(type(request[name]) is not dict
                   for name in ("baseline", "left", "right"))
            or len(_canonical(request)) > MAX_REQUEST_BYTES):
        raise StudioQuestError("invalid typed Jeeves workflow merge request")
    _lease(request["expected_catalog_digest"], "Jeeves world merge catalog")
    result = merge_world_batch_plans(
        request["baseline"], request["left"], request["right"],
        authorized=True)
    if result["receipt"]["catalog_digest"] != request["expected_catalog_digest"]:
        raise StudioQuestError("stale Jeeves world workflow catalog")
    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "request_digest": _digest(request),
        "merge": result,
        "source_replay_verified": True,
        "file_write_performed": False,
        "native_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_RESULT_BYTES - 128:
        raise StudioQuestError("Jeeves world workflow merge result exceeds budget")
    payload["result_digest"] = _digest(payload)
    return payload
