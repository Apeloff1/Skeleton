"""Typed Jeeves tool for canonical offline story preview and checkpoint diff.

The model supplies only data. Operator authorization is external, the project
is read from the original catalog, and untrusted browser JSON is independently
replayed by the canonical Python quest runtime. No file writes are performed.
"""
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
from skeleton.ai.game_builder.studio_ecosystem_story_review import (
    compare_browser_story_receipts, preview_browser_story_choice,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_story_checkpoint_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_story_checkpoint_result.v1"
_FIELDS = frozenset({
    "schema", "project_id", "expected_quest_source_digest",
    "operation", "current_checkpoint", "candidate_checkpoint",
    "stage_id", "alternative",
})
MAX_CHECKPOINT_BYTES = 65536
MAX_REQUEST_BYTES = 140000


def tool_schema() -> dict[str, object]:
    """Closed typed discovery contract, not a grant of write authority."""
    return {
        "name": "studio_original_story_checkpoint",
        "description": "Preview authored choices or compare browser checkpoints by canonical replay",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{2,75}$"},
                "expected_quest_source_digest": {
                    "type": "string", "pattern": "^[0-9a-f]{64}$"},
                "operation": {"type": "string", "enum": ["preview", "compare"]},
                "current_checkpoint": {"type": "string", "maxLength": MAX_CHECKPOINT_BYTES},
                "candidate_checkpoint": {
                    "type": ["string", "null"], "maxLength": MAX_CHECKPOINT_BYTES},
                "stage_id": {"type": ["string", "null"], "maxLength": 256},
                "alternative": {"type": ["string", "null"], "maxLength": 256},
            },
            "required": sorted(_FIELDS),
        },
    }


def _raw(value: object, kind: str) -> bytes:
    if type(value) is not str:
        raise StudioQuestError("invalid " + kind + " checkpoint type")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise StudioQuestError("invalid " + kind + " checkpoint encoding") from exc
    if not 1 <= len(raw) <= MAX_CHECKPOINT_BYTES:
        raise StudioQuestError("missing or oversized " + kind + " checkpoint")
    return raw


def execute_story_checkpoint_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, object]:
    """Execute one source-leased, nonmutating, canonical replay operation."""
    if authorized is not True:
        raise PermissionError("Jeeves story checkpoint requires operator authorization")
    if type(request) is not dict or set(request) != _FIELDS:
        raise StudioQuestError("Jeeves story checkpoint requires exact typed fields")
    if request["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves story checkpoint schema")
    project = request["project_id"]
    if type(project) is not str or not IDENT.fullmatch(project):
        raise StudioQuestError("invalid Jeeves story checkpoint project")
    expected = _lease(request["expected_quest_source_digest"],
                      "Jeeves story quest source")
    operation = request["operation"]
    if type(operation) is not str or operation not in ("preview", "compare"):
        raise StudioQuestError("unsupported story checkpoint operation")
    if len(_canonical(request)) > MAX_REQUEST_BYTES:
        raise StudioQuestError("oversized Jeeves story checkpoint request")
    raw = _raw(request["current_checkpoint"], "current")
    documents = read_blueprint(project)
    program = compile_quest_program(documents)
    if program.source_digest != expected or program.project_id != project:
        raise StudioQuestError("stale Jeeves story checkpoint source lease")
    if operation == "preview":
        if (type(request["stage_id"]) is not str
                or type(request["alternative"]) is not str
                or request["candidate_checkpoint"] is not None):
            raise StudioQuestError("invalid preview-only story checkpoint fields")
        proof = preview_browser_story_choice(
            raw, documents, stage=request["stage_id"],
            alternative=request["alternative"], authorized=True)
    else:
        if (request["stage_id"] is not None
                or request["alternative"] is not None):
            raise StudioQuestError("invalid comparison-only story checkpoint fields")
        candidate = _raw(request["candidate_checkpoint"], "candidate")
        proof = compare_browser_story_receipts(
            raw, candidate, documents, authorized=True)
    if proof["project_id"] != project or proof["source_digest"] != expected:
        raise StudioQuestError("Jeeves story replay source identity mismatch")
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "project_id": project,
        "operation": operation,
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
