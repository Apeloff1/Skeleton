"""Typed Jeeves original story reader bookmark with canonical source replay."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_story_reading_bookmark import (
    REQUEST_SCHEMA as BOOKMARK_REQUEST_SCHEMA,
    compile_story_reading_bookmark, render_story_reading_bookmark_html,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_story_reading_bookmark_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_story_reading_bookmark_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_quest_source_digest",
    "stage_id", "reader_note", "format",
})


def story_reading_bookmark_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_story_reading_bookmark",
        "description": "Save source-bound reader position or review authored scene context",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_quest_source_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "stage_id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]{1,128}$"},
                "reader_note": {"type": "string", "minLength": 1, "maxLength": 240},
                "format": {"type": "string", "enum": ["json", "html"]},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_story_reading_bookmark_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("Jeeves story bookmark requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves story bookmark requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves story bookmark schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves story bookmark project")
    expected = _lease(request["expected_quest_source_digest"],
                      "Jeeves story bookmark source")
    kind = request["format"]
    if type(kind) is not str or kind not in ("json", "html"):
        raise StudioQuestError("invalid Jeeves story bookmark format")
    if len(_canonical(request)) > 2048:
        raise StudioQuestError("oversized Jeeves story bookmark request")
    documents = read_blueprint(project)
    receipt = compile_story_reading_bookmark(
        documents, {
            "schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": request["stage_id"],
            "reader_note": request["reader_note"],
        }, authorized=True, expected_source_digest=expected)
    content = (_canonical(receipt).decode("ascii") + "\n" if kind == "json" else
               render_story_reading_bookmark_html(
                   documents, receipt, authorized=True,
                   expected_source_digest=expected).decode("utf-8"))
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "source_digest": expected, "format": kind,
        "content": content, "content_sha256": sha256(content.encode()).hexdigest(),
        "bookmark_digest": receipt["bookmark_digest"],
        "stage_index": receipt["stage_index"],
        "stage_count": receipt["stage_count"],
        "sandbox_playable_html_sha256": receipt["sandbox_playable_html_sha256"],
        "reading_position_only": True, "quest_action_committed": False,
        "file_write_performed": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
