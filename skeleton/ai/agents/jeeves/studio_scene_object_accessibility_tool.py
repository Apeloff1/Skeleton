"""Typed Jeeves authoring of canonical scene-object accessibility descriptions."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_scene_object_accessibility import (
    REQUEST_SCHEMA as SOURCE_REQUEST_SCHEMA,
    compile_scene_object_accessibility, render_scene_object_accessibility_html,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_scene_object_accessibility_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_scene_object_accessibility_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_quest_source_digest",
    "scene_id", "labels", "format",
})


def scene_object_accessibility_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_scene_object_accessibility",
        "description": "Author complete source-bound accessible descriptions of scene objects",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_quest_source_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "labels": {
                    "type": "object", "minProperties": 1, "maxProperties": 64,
                    "additionalProperties": {"type": "string", "minLength": 1,
                                             "maxLength": 240},
                },
                "format": {"type": "string", "enum": ["json", "html"]},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_scene_object_accessibility_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("Jeeves scene accessibility requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves scene accessibility requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves scene accessibility schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves scene accessibility project")
    expected = _lease(request["expected_quest_source_digest"],
                      "Jeeves scene accessibility source")
    kind = request["format"]
    if type(kind) is not str or kind not in ("json", "html"):
        raise StudioQuestError("invalid Jeeves scene accessibility format")
    if len(_canonical(request)) > 32768:
        raise StudioQuestError("oversized Jeeves scene accessibility request")
    documents = read_blueprint(project)
    receipt = compile_scene_object_accessibility(
        documents, {
            "schema": SOURCE_REQUEST_SCHEMA,
            "scene_id": request["scene_id"], "labels": request["labels"],
        }, authorized=True, expected_source_digest=expected)
    content = (_canonical(receipt).decode("ascii") + "\n" if kind == "json" else
               render_scene_object_accessibility_html(
                   documents, receipt, authorized=True,
                   expected_source_digest=expected).decode("utf-8"))
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "source_digest": expected, "format": kind,
        "content": content,
        "content_sha256": sha256(content.encode()).hexdigest(),
        "accessibility_digest": receipt["accessibility_digest"],
        "scene_id": receipt["scene_id"], "object_count": receipt["object_count"],
        "source_object_coverage_complete": True,
        "sandbox_playable_html_sha256": receipt["sandbox_playable_html_sha256"],
        "file_write_performed": False,
        "asset_rendered": False, "accessibility_device_verified": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
