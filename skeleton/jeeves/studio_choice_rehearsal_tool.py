"""Operator-gated Jeeves adapter for source-bound offline quest-choice edits.

The model may propose a typed export, but cannot authorize itself or persist
game state. Only canonical quest replay can accept the proposed history.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import IDENT, read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_director_choice_rehearsal import (
    replay_choice_export,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_choice_rehearsal_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_choice_rehearsal_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_source_digest",
    "expected_session_digest", "export",
})
MAX_TOOL_BYTES = 20 * 1024


def tool_schema() -> dict[str, object]:
    """Typed tool discovery descriptor; never an authorization grant."""
    return {
        "name": "studio_original_choice_rehearsal",
        "description": "Replay source-leased offline quest-choice edits without file writes",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "export": {"type": "object", "additionalProperties": True},
            },
            "required": sorted(_FIELDS),
        },
    }


def execute_choice_rehearsal_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    """Validate typed request, independently replay, and return a bounded proof."""
    if authorized is not True:
        raise PermissionError("Jeeves choice rehearsal requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves choice rehearsal requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves choice rehearsal schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves choice rehearsal project")
    source = _lease(request["expected_source_digest"], "Jeeves choice source")
    session = _lease(request["expected_session_digest"], "Jeeves choice session")
    if type(request["export"]) is not dict or len(_canonical(request)) > MAX_TOOL_BYTES:
        raise StudioQuestError("invalid or oversized Jeeves choice export")
    documents = read_blueprint(project)
    proof = replay_choice_export(
        documents, request["export"], authorized=True,
        expected_source_digest=source, expected_session_digest=session)
    if proof["project_id"] != project:
        raise StudioQuestError("Jeeves choice export project mismatch")
    payload: dict[str, object] = {
        "schema": RESULT_SCHEMA, "project_id": project,
        "request_digest": sha256(_canonical(request)).hexdigest(),
        "canonical_replay": proof, "file_write_performed": False,
        "browser_export_trusted": False, "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload
