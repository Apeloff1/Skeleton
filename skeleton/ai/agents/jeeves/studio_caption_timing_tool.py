"""Typed Jeeves adapter for source-bound human caption timing and HTML review."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from skeleton.ai.game_builder.studio_ecosystem_caption_timing import (
    compile_caption_timing_edit, render_caption_timing_review_html,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_caption_timing_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_caption_timing_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_quest_source_digest", "edits_ms", "format",
})


def caption_timing_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_caption_timing",
        "description": "Edit synthetic caption timings without changing authored words",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_quest_source_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "edits_ms": {
                    "type": "object", "minProperties": 1, "maxProperties": 64,
                    "patternProperties": {
                        "^[1-9][0-9]*$": {
                            "type": "integer", "minimum": 1000, "maximum": 30000}},
                    "additionalProperties": False,
                },
                "format": {"type": "string", "enum": ["webvtt", "html"]},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_caption_timing_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("Jeeves caption timing requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves caption timing requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves caption timing schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid caption timing project")
    source_digest = _lease(
        request["expected_quest_source_digest"], "Jeeves caption timing source")
    kind = request["format"]
    if type(kind) is not str or kind not in ("webvtt", "html"):
        raise StudioQuestError("invalid caption timing format")
    if len(_canonical(request)) > 8192:
        raise StudioQuestError("oversized Jeeves caption timing request")
    documents = read_blueprint(project)
    receipt = compile_caption_timing_edit(
        documents, request["edits_ms"], authorized=True,
        expected_source_digest=source_digest)
    content = (receipt["webvtt"] if kind == "webvtt" else
               render_caption_timing_review_html(
                   documents, receipt, authorized=True,
                   expected_source_digest=source_digest).decode("utf-8"))
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "source_digest": source_digest, "format": kind,
        "content": content,
        "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
        "edit_digest": receipt["edit_digest"],
        "canonical_manifest_digest": receipt["canonical_manifest_digest"],
        "operator_changed_count": receipt["operator_changed_count"],
        "caption_count": receipt["caption_count"],
        "synthetic_duration_ms": receipt["synthetic_duration_ms"],
        "canonical_words_preserved": True, "file_write_performed": False,
        "audio_rendered": False, "audio_sync_verified": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
