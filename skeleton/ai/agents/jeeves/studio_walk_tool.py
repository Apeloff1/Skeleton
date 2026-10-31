"""Operator-authorized Jeeves tool for deterministic original-world walk sessions.

This is a typed adapter over the canonical studio catalog and walk replay engine,
not a second game state implementation or a model-provider authorization route.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
    DIRECTIONS, MAX_WALK_EVENTS, MAX_WALK_RECEIPT_BYTES, compare_walk_sessions,
    export_walk_receipt, follow_walk_route, replay_walk,
    restore_walk_receipt, validate_walk_events, walk_branch_forecast,
    walk_checkpoint_timeline, walk_choice_previews, walk_narrative_continuity,
    walk_route_hint,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_walk_tool_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_walk_tool_result.v1"
OPERATIONS = frozenset({
    "replay", "route", "follow_route", "choices", "forecast", "continuity",
    "timeline", "compare", "coverage", "transcript", "journal",
})
_ALLOWED = frozenset({"schema", "project_id", "operation", "events", "receipt",
                      "forecast_depth", "compare_events", "transcript_offset",
                      "transcript_limit", "transcript_expected_digest",
                      "journal_offset", "journal_limit", "journal_expected_session_digest",
                      "journal_expected_source_digest"})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical Jeeves walk tool request") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _validate_tool_events(events: list[object]) -> None:
    validate_walk_events(events)
    for kind, value in events:
        if kind == "move" and value not in DIRECTIONS:
            raise StudioQuestError("unknown Jeeves walk direction")
        if kind not in ("move", "choose"):
            raise StudioQuestError("unknown Jeeves walk action")


def tool_schema() -> dict[str, object]:
    """Typed descriptor for trusted Jeeves tool discovery, not authorization."""
    return {
        "name": "studio_authoritative_walk",
        "description": "Source-verified offline original-world gameplay; operator authorization required",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "operation": {"type": "string", "enum": sorted(OPERATIONS)},
                "events": {"type": "array", "maxItems": MAX_WALK_EVENTS,
                           "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                     "items": {"type": "string"}}},
                "receipt": {"type": ["object", "null"]},
                "forecast_depth": {"type": "integer", "minimum": 1, "maximum": 3},
                "journal_offset": {"type": "integer", "minimum": 0},
                "journal_limit": {"type": "integer", "minimum": 1, "maximum": 8},
                "journal_expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "journal_expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "transcript_offset": {"type": "integer", "minimum": 0},
                "transcript_limit": {"type": "integer", "minimum": 1, "maximum": 32},
                "transcript_expected_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "compare_events": {"type": "array", "maxItems": MAX_WALK_EVENTS,
                                   "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                             "items": {"type": "string"}}},
            },
            "required": ["schema", "project_id", "operation", "events"],
        },
    }


def execute_walk_tool(request: Mapping[str, Any], *, authorized: bool = False) -> dict[str, Any]:
    """Plan -> authoritative replay -> verify -> source-bound result receipt.

    The caller must supply operator authority out of band. Untrusted tool
    arguments cannot grant permission, write files, or claim native evidence.
    """
    if authorized is not True:
        raise PermissionError("Jeeves walk tool requires operator authorization")
    if type(request) is not dict or set(request) - _ALLOWED:
        raise StudioQuestError("invalid Jeeves walk tool fields")
    if request.get("schema") != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves walk tool request schema")
    project = request.get("project_id")
    operation = request.get("operation")
    if (type(project) is not str or not 1 <= len(project) <= 128
            or type(operation) is not str or operation not in OPERATIONS):
        raise StudioQuestError("invalid Jeeves walk tool project or operation")
    events = request.get("events")
    if type(events) is not list:
        raise StudioQuestError("Jeeves walk tool events must be a list")
    _validate_tool_events(events)
    depth = request.get("forecast_depth", 2)
    if (type(depth) is not int or not 1 <= depth <= 3
            or ("forecast_depth" in request and operation != "forecast")):
        raise StudioQuestError("invalid Jeeves walk forecast depth")
    comparison = request.get("compare_events")
    if operation == "compare":
        if type(comparison) is not list:
            raise StudioQuestError("compare requires a complete event list")
        _validate_tool_events(comparison)
    elif "compare_events" in request:
        raise StudioQuestError("compare_events requires compare operation")
    transcript_offset = request.get("transcript_offset", 0)
    transcript_limit = request.get("transcript_limit", 32)
    transcript_expected = request.get("transcript_expected_digest")
    if (type(transcript_offset) is not int or transcript_offset < 0
            or type(transcript_limit) is not int or not 1 <= transcript_limit <= 32
            or (transcript_expected is not None and
                (type(transcript_expected) is not str or
                 len(transcript_expected) != 64 or
                 any(c not in "0123456789abcdef" for c in transcript_expected)))
            or (operation != "transcript" and any(
                field in request for field in (
                    "transcript_offset", "transcript_limit", "transcript_expected_digest"
                )))):
        raise StudioQuestError("invalid Jeeves transcript continuation arguments")
    journal_offset = request.get("journal_offset", 0)
    journal_limit = request.get("journal_limit", 8)
    journal_session = request.get("journal_expected_session_digest")
    journal_source = request.get("journal_expected_source_digest")
    if (type(journal_offset) is not int or journal_offset < 0
            or type(journal_limit) is not int or not 1 <= journal_limit <= 8
            or any(value is not None and
                   (type(value) is not str or len(value) != 64 or
                    any(ch not in "0123456789abcdef" for ch in value))
                   for value in (journal_session, journal_source))
            or (operation != "journal" and any(
                field in request for field in (
                    "journal_offset", "journal_limit", "journal_expected_session_digest",
                    "journal_expected_source_digest"
                )))):
        raise StudioQuestError("invalid Jeeves canon journal arguments")
    raw_receipt = request.get("receipt")
    if raw_receipt is not None and type(raw_receipt) is not dict:
        raise StudioQuestError("invalid Jeeves walk receipt type")
    encoded = _canonical(request)
    if len(encoded) > MAX_WALK_RECEIPT_BYTES:
        raise StudioQuestError("Jeeves walk tool request exceeds byte budget")
    docs = read_blueprint(project)
    previous = (restore_walk_receipt(docs, _canonical(raw_receipt), authorized=True)
                if raw_receipt is not None else None)
    prior = previous.events if previous is not None else ()
    if len(prior) + len(events) > MAX_WALK_EVENTS:
        raise StudioQuestError("Jeeves walk tool replay exceeds event budget")
    session = replay_walk(docs, list(prior) + events, authorized=True)
    if session.project_id != project:
        raise StudioQuestError("Jeeves walk source project mismatch")
    detail: object = None
    if operation == "route":
        detail = walk_route_hint(session, docs, authorized=True)
    elif operation == "follow_route":
        session, detail = follow_walk_route(session, docs, authorized=True)
    elif operation == "choices":
        detail = walk_choice_previews(session, docs, authorized=True)
    elif operation == "forecast":
        detail = walk_branch_forecast(session, docs, depth=depth, authorized=True)
    elif operation == "coverage":
        from skeleton.ai.game_builder.studio_ecosystem_walk_coverage import (
            audit_walk_choice_coverage,
        )
        detail = audit_walk_choice_coverage(session, docs, authorized=True)
    elif operation == "continuity":
        detail = walk_narrative_continuity(session, docs, authorized=True)
    elif operation == "timeline":
        detail = walk_checkpoint_timeline(session, docs, authorized=True)
    elif operation == "journal":
        from skeleton.ai.game_builder.studio_ecosystem_walk_canon_journal import (
            walk_canon_journal,
        )
        detail = walk_canon_journal(
            session, docs, authorized=True, offset=journal_offset, limit=journal_limit,
            expected_session_digest=journal_session,
            expected_source_digest=journal_source,
        )
    elif operation == "transcript":
        from skeleton.ai.game_builder.studio_ecosystem_walk_story_transcript import (
            walk_story_transcript,
        )
        detail = walk_story_transcript(
            session, docs, authorized=True, offset=transcript_offset,
            max_scenes=transcript_limit,
            expected_session_digest=transcript_expected,
        )
    elif operation == "compare":
        other = replay_walk(docs, comparison, authorized=True)
        detail = compare_walk_sessions(session, other, docs, authorized=True)
    saved = export_walk_receipt(session, docs, authorized=True)
    verified = restore_walk_receipt(docs, saved, authorized=True)
    if verified != session:
        raise StudioQuestError("Jeeves walk tool replay verification mismatch")
    payload = {
        "schema": RESULT_SCHEMA, "operation": operation, "project_id": project,
        "request_digest": _digest(request), "receipt": json.loads(saved),
        "detail": detail, "source_digest": session.source_digest,
        "replay_verified": True, "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


# The catalog audit has its own typed tool: it never invents a project ID to
# satisfy the single-game replay contract, and has no provider or write path.
CATALOG_REQUEST_SCHEMA = "skeleton.jeeves.studio_walk_catalog_request.v1"
CATALOG_RESULT_SCHEMA = "skeleton.jeeves.studio_walk_catalog_result.v1"
_CATALOG_FIELDS = frozenset({"schema", "offset", "limit", "genre", "biome", "expected_catalog_digest"})


def catalog_tool_schema() -> dict[str, object]:
    """Discoverable operator-gated read-only catalog QA tool descriptor."""
    return {
        "name": "studio_authoritative_walk_catalog",
        "description": "Bounded source-verified original game catalog choice audit",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": CATALOG_REQUEST_SCHEMA},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 4},
                "genre": {"type": ["string", "null"], "maxLength": 96},
                "biome": {"type": ["string", "null"], "maxLength": 96},
                "expected_catalog_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": ["schema", "offset", "limit"],
        },
    }


def execute_catalog_audit_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    """Verify typed request before loading the canonical catalog or any source."""
    if authorized is not True:
        raise PermissionError("Jeeves catalog audit requires operator authorization")
    if type(request) is not dict or set(request) - _CATALOG_FIELDS:
        raise StudioQuestError("invalid Jeeves catalog audit fields")
    if request.get("schema") != CATALOG_REQUEST_SCHEMA:
        raise StudioQuestError("unsupported Jeeves catalog audit schema")
    offset, limit = request.get("offset"), request.get("limit")
    genre, biome = request.get("genre"), request.get("biome")
    expected = request.get("expected_catalog_digest")
    if "expected_catalog_digest" in request and expected is None:
        raise StudioQuestError("null catalog continuation digest is not permitted")
    if (type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= 4
            or any(value is not None and
                   (type(value) is not str or not value or len(value) > 96)
                   for value in (genre, biome))):
        raise StudioQuestError("invalid Jeeves catalog audit bounds")
    if (expected is not None and
            (type(expected) is not str or len(expected) != 64 or
             any(c not in "0123456789abcdef" for c in expected))):
        raise StudioQuestError("invalid Jeeves catalog continuation digest")
    if offset and expected is None:
        raise StudioQuestError("Jeeves catalog continuation requires a digest")
    encoded = _canonical(request)
    if len(encoded) > 4096:
        raise StudioQuestError("Jeeves catalog audit request exceeds byte budget")
    from skeleton.ai.game_builder.studio_ecosystem_walk_coverage_batch import (
        audit_catalog_walk_choices,
    )
    detail = audit_catalog_walk_choices(
        authorized=True, genre=genre, biome=biome, offset=offset, limit=limit,
        expected_catalog_digest=expected,
    )
    payload = {
        "schema": CATALOG_RESULT_SCHEMA,
        "request_digest": _digest(request),
        "catalog_digest": detail["catalog_digest"],
        "detail": detail,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload



CATALOG_MERGE_REQUEST_SCHEMA = "skeleton.jeeves.studio_walk_catalog_merge_request.v1"
CATALOG_MERGE_RESULT_SCHEMA = "skeleton.jeeves.studio_walk_catalog_merge_result.v1"


def catalog_merge_tool_schema() -> dict[str, object]:
    """Typed, operator-gated, source-revalidated catalog page aggregation."""
    return {
        "name": "studio_authoritative_walk_catalog_merge",
        "description": "Revalidate and aggregate up to four canonical catalog audit pages",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": CATALOG_MERGE_REQUEST_SCHEMA},
                "pages": {"type": "array", "minItems": 1, "maxItems": 4,
                          "items": {"type": "object"}},
            },
            "required": ["schema", "pages"],
        },
    }


def execute_catalog_merge_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    """Re-read source for every supplied page, never trust client audit flags."""
    if authorized is not True:
        raise PermissionError("Jeeves catalog merge requires operator authorization")
    if (type(request) is not dict or set(request) != {"schema", "pages"}
            or request.get("schema") != CATALOG_MERGE_REQUEST_SCHEMA):
        raise StudioQuestError("invalid Jeeves catalog merge request")
    pages = request["pages"]
    if type(pages) is not list or not 1 <= len(pages) <= 4:
        raise StudioQuestError("invalid Jeeves catalog merge page count")
    if len(_canonical(request)) > 131_072:
        raise StudioQuestError("Jeeves catalog merge exceeds byte budget")
    from skeleton.ai.game_builder.studio_ecosystem_walk_coverage_batch import (
        merge_catalog_walk_audits,
    )
    detail = merge_catalog_walk_audits(pages, authorized=True)
    payload = {
        "schema": CATALOG_MERGE_RESULT_SCHEMA,
        "request_digest": _digest(request),
        "catalog_digest": detail["catalog_digest"],
        "detail": detail,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


CANON_PROOF_REQUEST_SCHEMA = "skeleton.jeeves.studio_canon_proof_request.v1"
CANON_PROOF_RESULT_SCHEMA = "skeleton.jeeves.studio_canon_proof_result.v1"


def canon_proof_tool_schema() -> dict[str, object]:
    """Discoverable, operator-gated original-world contradiction checker."""
    return {
        "name": "studio_canon_proof",
        "description": "Audit source-bound era, scene, quest, cast and ending obligations",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": CANON_PROOF_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["schema", "project_id"],
        },
    }


def execute_canon_proof_tool(request: Mapping[str, Any], *,
                             authorized: bool = False) -> dict[str, Any]:
    """Read canonical authored sections without a model or side effects."""
    if authorized is not True:
        raise PermissionError("Jeeves canon proof requires operator authorization")
    if (type(request) is not dict or set(request) != {"schema", "project_id"}
            or request.get("schema") != CANON_PROOF_REQUEST_SCHEMA):
        raise StudioQuestError("invalid Jeeves canon proof request")
    project = request["project_id"]
    if type(project) is not str or not 1 <= len(project) <= 128:
        raise StudioQuestError("invalid Jeeves canon proof project")
    if len(_canonical(request)) > 4096:
        raise StudioQuestError("Jeeves canon proof request exceeds byte budget")
    from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
    detail = audit_canon_source(read_blueprint(project), authorized=True)
    if detail["project_id"] != project:
        raise StudioQuestError("Jeeves canon proof project/source mismatch")
    payload = {
        "schema": CANON_PROOF_RESULT_SCHEMA,
        "project_id": project, "request_digest": _digest(request),
        "detail": detail, "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


AUTHOR_REVISION_REQUEST_SCHEMA = "skeleton.jeeves.studio_author_revision_request.v1"
AUTHOR_REVISION_RESULT_SCHEMA = "skeleton.jeeves.studio_author_revision_result.v1"

def author_revision_tool_schema() -> dict[str, object]:
    """Typed operator-authorized prose editor preview; no model-owned file writes."""
    return {
        "name": "studio_author_revision",
        "description": "Preview canon-safe original edits and compile an offline playable story",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": AUTHOR_REVISION_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "edits": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "object"}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "edits"],
        },
    }

def execute_author_revision_tool(request: Mapping[str, Any], *,
                                 authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves authored revision requires operator authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "project_id", "expected_source_digest", "edits"}
            or request.get("schema") != AUTHOR_REVISION_REQUEST_SCHEMA):
        raise StudioQuestError("invalid typed Jeeves authored revision request")
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
        REVISION_SCHEMA, preview_canon_revision,
    )
    source_request = dict(request)
    source_request["schema"] = REVISION_SCHEMA
    _, _, receipt = preview_canon_revision(
        read_blueprint(request["project_id"]), source_request, authorized=True,
    )
    payload = {
        "schema": AUTHOR_REVISION_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": receipt,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload
