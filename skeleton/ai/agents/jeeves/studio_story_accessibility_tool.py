"""Typed Jeeves source-leased accessible story reading and caption compiler."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program,
)
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)
from skeleton.ai.game_builder.studio_ecosystem_story_accessibility import (
    compile_story_accessibility,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_story_accessibility_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_story_accessibility_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_quest_source_digest", "format",
})


def story_accessibility_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_story_accessibility",
        "description": "Compile authored original story to a screen-reader script or synthetic WebVTT",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_quest_source_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "format": {"type": "string", "enum": ["markdown", "webvtt"]},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_story_accessibility_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("Jeeves accessibility requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves accessibility requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves accessibility schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid accessibility project")
    expected = _lease(request["expected_quest_source_digest"],
                      "Jeeves accessibility quest source")
    kind = request["format"]
    if type(kind) is not str or kind not in ("markdown", "webvtt"):
        raise StudioQuestError("invalid accessibility output format")
    if len(_canonical(request)) > 2048:
        raise StudioQuestError("oversized accessibility request")
    documents = read_blueprint(project)
    program = compile_quest_program(documents)
    if program.project_id != project or program.source_digest != expected:
        raise StudioQuestError("stale accessibility source lease")
    compiled = compile_story_accessibility(documents, authorized=True)
    if compiled["source_digest"] != expected:
        raise StudioQuestError("accessibility source changed during compile")
    content = compiled["markdown" if kind == "markdown" else "webvtt"]
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "project_id": project,
        "source_digest": expected,
        "format": kind,
        "content": content,
        "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
        "manifest_digest": compiled["manifest_digest"],
        "caption_count": compiled["caption_count"],
        "synthetic_duration_ms": compiled["synthetic_duration_ms"],
        "file_write_performed": False,
        "audio_rendered": False,
        "audio_sync_verified": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
