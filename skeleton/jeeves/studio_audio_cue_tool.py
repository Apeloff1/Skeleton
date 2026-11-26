"""Typed operator-gated Jeeves bridge for original scene audio and caption plans."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_audio_cues import (
    REQUEST_SCHEMA as AUTHORING_SCHEMA, compile_audio_cues,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease

REQUEST_SCHEMA = "skeleton.jeeves.studio_audio_cue_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_audio_cue_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_source_digest", "expected_session_digest",
    "actions", "schedule", "authoring",
})


def audio_cue_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_audio_caption_cues",
        "description": (
            "Compile authored caption and audio-layer timing against source-leased "
            "quest and scene replay; no audio generation, file writes, or release claims"
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
                "authoring": {"type": "object", "properties": {
                    "schema": {"type": "string", "const": AUTHORING_SCHEMA},
                    "scene_cues": {"type": "object"},
                }, "required": ["schema", "scene_cues"], "additionalProperties": False},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_audio_cue_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves audio cue authoring requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("invalid Jeeves audio cue envelope")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves audio cue schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves audio cue project")
    source = _lease(request["expected_source_digest"], "Jeeves audio source")
    session = _lease(request["expected_session_digest"], "Jeeves audio session")
    if (type(request["actions"]) is not list
            or type(request["schedule"]) is not dict
            or type(request["authoring"]) is not dict
            or len(_canonical(request)) > 64 * 1024):
        raise StudioQuestError("invalid or oversized Jeeves audio cue authoring")
    detail = compile_audio_cues(
        read_blueprint(project), request["actions"], request["schedule"],
        request["authoring"], authorized=True,
        expected_source_digest=source, expected_session_digest=session)
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "source_replay_verified": True,
        "audio_recorded_verified": False, "caption_runtime_verified": False,
        "native_audio_verified": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
