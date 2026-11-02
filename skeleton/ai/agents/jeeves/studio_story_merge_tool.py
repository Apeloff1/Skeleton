"""Closed-schema Jeeves adapter for three-way offline story checkpoint merge."""
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
from skeleton.ai.game_builder.studio_ecosystem_story_merge import (
    merge_browser_story_checkpoints,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_story_merge_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_story_merge_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_quest_source_digest",
    "ancestor_checkpoint", "current_checkpoint", "candidate_checkpoint",
})
MAX_CHECKPOINT_BYTES = 65536
MAX_REQUEST_BYTES = 205000


def story_merge_tool_schema() -> dict[str, object]:
    return {
        "name": "studio_original_story_checkpoint_merge",
        "description": "Reconcile two source-bound offline story forks against their exact ancestor",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_quest_source_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "ancestor_checkpoint": {"type": "string", "maxLength": MAX_CHECKPOINT_BYTES},
                "current_checkpoint": {"type": "string", "maxLength": MAX_CHECKPOINT_BYTES},
                "candidate_checkpoint": {"type": "string", "maxLength": MAX_CHECKPOINT_BYTES},
            },
            "required": sorted(_FIELDS),
        },
    }


def _raw(value: object, name: str) -> bytes:
    if type(value) is not str:
        raise StudioQuestError("invalid " + name + " checkpoint type")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise StudioQuestError("invalid " + name + " checkpoint encoding") from exc
    if not 1 <= len(raw) <= MAX_CHECKPOINT_BYTES:
        raise StudioQuestError("missing or oversized " + name + " checkpoint")
    return raw


def execute_story_merge_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("Jeeves story merge requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves story merge requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves story merge schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves story merge project")
    expected = _lease(request["expected_quest_source_digest"],
                      "Jeeves story merge quest source")
    if len(_canonical(request)) > MAX_REQUEST_BYTES:
        raise StudioQuestError("oversized Jeeves story merge request")
    documents = read_blueprint(project)
    program = compile_quest_program(documents)
    if program.project_id != project or program.source_digest != expected:
        raise StudioQuestError("stale Jeeves story merge source lease")
    proof = merge_browser_story_checkpoints(
        _raw(request["ancestor_checkpoint"], "ancestor"),
        _raw(request["current_checkpoint"], "current"),
        _raw(request["candidate_checkpoint"], "candidate"),
        documents, authorized=True,
    )
    if proof["project_id"] != project or proof["source_digest"] != expected:
        raise StudioQuestError("Jeeves merge replay source identity mismatch")
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "project_id": project,
        "request_digest": sha256(_canonical(request)).hexdigest(),
        "canonical_replay": proof,
        "file_write_performed": False,
        "browser_checkpoint_trusted": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
