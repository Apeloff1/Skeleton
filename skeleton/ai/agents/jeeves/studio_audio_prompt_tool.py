"""Operator-authorized Jeeves prompt-to-source audio cue planner."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_audio_prompt import propose_audio_from_prompt
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease

REQUEST_SCHEMA = "skeleton.jeeves.studio_audio_prompt_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_audio_prompt_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_source_digest", "expected_session_digest",
    "actions", "schedule", "prompt",
})


def audio_prompt_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_audio_prompt_planner",
        "description": (
            "Plan editable original audio/caption cues from user text and canonical "
            "scene source; deterministic fallback, no provider or native audio claims"
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64},
                "schedule": {"type": "object"},
                "prompt": {"type": "string", "minLength": 1, "maxLength": 512},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_audio_prompt_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves audio prompt planning requires operator authorization")
    if (type(request) is not dict or set(request) != _FIELDS
            or request.get("schema") != REQUEST_SCHEMA):
        raise StudioQuestError("invalid typed Jeeves audio prompt request")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves audio prompt project")
    source = _lease(request["expected_source_digest"], "Jeeves prompt source")
    session = _lease(request["expected_session_digest"], "Jeeves prompt session")
    if (type(request["actions"]) is not list
            or type(request["schedule"]) is not dict
            or type(request["prompt"]) is not str
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid or oversized Jeeves audio prompt")
    detail = propose_audio_from_prompt(
        read_blueprint(project), request["actions"], request["schedule"],
        request["prompt"], authorized=True,
        expected_source_digest=source, expected_session_digest=session)
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "model_inference_performed": False,
        "audio_generated": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
