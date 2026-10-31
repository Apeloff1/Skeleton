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
    source = read_blueprint(request["project_id"])
    revised, _, receipt = preview_canon_revision(
        source, source_request, authorized=True,
    )
    from skeleton.ai.game_builder.studio_ecosystem_revision_impact import compare_revision_sources
    impact = compare_revision_sources(source, revised, authorized=True)
    payload = {
        "schema": AUTHOR_REVISION_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": receipt,
        "impact": impact,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


AUTHOR_MERGE_REQUEST_SCHEMA = "skeleton.jeeves.studio_author_merge_request.v1"
AUTHOR_MERGE_RESULT_SCHEMA = "skeleton.jeeves.studio_author_merge_result.v1"


def author_merge_tool_schema() -> dict[str, object]:
    """Typed, operator-gated merge preview; no model-controlled file writes."""
    return {
        "name": "studio_author_merge",
        "description": "Reconcile independently edited original prose against canonical source",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": AUTHOR_MERGE_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "left_edits": {"type": "array", "minItems": 1, "maxItems": 16,
                               "items": {"type": "object"}},
                "right_edits": {"type": "array", "minItems": 1, "maxItems": 16,
                                "items": {"type": "object"}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "left_edits", "right_edits"],
        },
    }


def execute_author_merge_tool(request: Mapping[str, Any], *,
                              authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves authored merge requires operator authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "project_id", "expected_source_digest",
                                "left_edits", "right_edits"}
            or request.get("schema") != AUTHOR_MERGE_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves authored merge request")
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
        REVISION_SCHEMA, preview_canon_revision,
    )
    from skeleton.ai.game_builder.studio_ecosystem_author_merge import merge_canon_revisions
    base = read_blueprint(request["project_id"])
    revisions = []
    for field in ("left_edits", "right_edits"):
        edit_request = {
            "schema": REVISION_SCHEMA,
            "project_id": request["project_id"],
            "expected_source_digest": request["expected_source_digest"],
            "edits": request[field],
        }
        revision, _, _ = preview_canon_revision(base, edit_request, authorized=True)
        revisions.append(revision)
    _, _, receipt, impact = merge_canon_revisions(
        base, revisions[0], revisions[1], authorized=True)
    result = {
        "schema": AUTHOR_MERGE_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "merge_receipt": receipt,
        "impact": impact,
        "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result



AUTHOR_CHERRY_PICK_REQUEST_SCHEMA = "skeleton.jeeves.studio_author_cherry_pick_request.v1"
AUTHOR_CHERRY_PICK_RESULT_SCHEMA = "skeleton.jeeves.studio_author_cherry_pick_result.v1"


def author_cherry_pick_tool_schema() -> dict[str, object]:
    """Discoverable operator-authorized selective source transplant preview."""
    return {
        "name": "studio_author_cherry_pick",
        "description": "Select source-leased original prose from a donor into a distinct revision",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": AUTHOR_CHERRY_PICK_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "donor_edits": {"type": "array", "minItems": 1, "maxItems": 16,
                                "items": {"type": "object"}},
                "target_edits": {"type": "array", "maxItems": 16,
                                 "items": {"type": "object"}},
                "selected_paths": {"type": "array", "minItems": 1, "maxItems": 16,
                                   "items": {"type": "array", "minItems": 2, "maxItems": 4}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "donor_edits", "target_edits", "selected_paths"],
        },
    }


def execute_author_cherry_pick_tool(request: Mapping[str, Any], *,
                                    authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves authored cherry-pick requires operator authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "project_id", "expected_source_digest",
                                "donor_edits", "target_edits", "selected_paths"}
            or request.get("schema") != AUTHOR_CHERRY_PICK_REQUEST_SCHEMA
            or len(_canonical(request)) > 32768):
        raise StudioQuestError("invalid typed Jeeves authored cherry-pick request")
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
        REVISION_SCHEMA, preview_canon_revision,
    )
    from skeleton.ai.game_builder.studio_ecosystem_author_cherry_pick import (
        cherry_pick_canon_revision,
    )
    from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
    base = read_blueprint(request["project_id"])
    proof = audit_canon_source(base, authorized=True)
    if request["expected_source_digest"] != proof["source_digest"]:
        raise StudioQuestError("stale Jeeves authored cherry-pick root")
    def preview(edits):
        return preview_canon_revision(base, {
            "schema": REVISION_SCHEMA, "project_id": request["project_id"],
            "expected_source_digest": proof["source_digest"], "edits": edits,
        }, authorized=True)[0]
    donor = preview(request["donor_edits"])
    target_edits = request["target_edits"]
    if type(target_edits) is not list:
        raise StudioQuestError("invalid Jeeves cherry-pick target edits")
    target = preview(target_edits) if target_edits else base
    _, _, receipt, impact = cherry_pick_canon_revision(
        base, donor, target, request["selected_paths"], authorized=True)
    payload = {
        "schema": AUTHOR_CHERRY_PICK_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": receipt, "impact": impact,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


AUTHOR_LINEAGE_REQUEST_SCHEMA = "skeleton.jeeves.studio_author_lineage_request.v1"
AUTHOR_LINEAGE_RESULT_SCHEMA = "skeleton.jeeves.studio_author_lineage_result.v1"


def author_lineage_tool_schema() -> dict[str, object]:
    """Typed preview of a chain of source-leased edits, with no file access."""
    return {
        "name": "studio_author_lineage",
        "description": "Verify an original authored revision chain and its replay leases",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": AUTHOR_LINEAGE_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "edit_batches": {"type": "array", "minItems": 1, "maxItems": 8,
                                 "items": {"type": "array", "minItems": 1,
                                           "maxItems": 16, "items": {"type": "object"}}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "edit_batches"],
        },
    }


def execute_author_lineage_tool(request: Mapping[str, Any], *,
                                authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves authored lineage requires operator authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "project_id", "expected_source_digest",
                                "edit_batches"}
            or request.get("schema") != AUTHOR_LINEAGE_REQUEST_SCHEMA
            or len(_canonical(request)) > 32768):
        raise StudioQuestError("invalid typed Jeeves authored lineage request")
    batches = request["edit_batches"]
    if type(batches) is not list or not 1 <= len(batches) <= 8:
        raise StudioQuestError("invalid Jeeves authored lineage batch count")
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
        REVISION_SCHEMA, preview_canon_revision,
    )
    from skeleton.ai.game_builder.studio_ecosystem_author_lineage import trace_canon_lineage
    from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
    base = read_blueprint(request["project_id"])
    proof = audit_canon_source(base, authorized=True)
    if request["expected_source_digest"] != proof["source_digest"]:
        raise StudioQuestError("stale Jeeves authored lineage root")
    steps = []
    source = base
    for edits in batches:
        source, _, receipt = preview_canon_revision(
            source, {
                "schema": REVISION_SCHEMA,
                "project_id": request["project_id"],
                "expected_source_digest": audit_canon_source(
                    source, authorized=True)["source_digest"],
                "edits": edits,
            }, authorized=True)
        steps.append((source, receipt))
    detail = trace_canon_lineage(base, steps, authorized=True)
    payload = {
        "schema": AUTHOR_LINEAGE_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


ENDING_PLAN_REQUEST_SCHEMA = "skeleton.jeeves.studio_ending_plan_request.v1"
ENDING_PLAN_RESULT_SCHEMA = "skeleton.jeeves.studio_ending_plan_result.v1"


def ending_plan_tool_schema() -> dict[str, object]:
    """Discoverable offline quest plan, not a promise of a reachable ending."""
    return {
        "name": "studio_ending_plan",
        "description": "Replay-verify an authored sandbox ending itinerary and expose external holds",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": ENDING_PLAN_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "ending_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "preferred_choices": {"type": "object", "maxProperties": 64,
                                      "additionalProperties": {"type": "string"}},
            },
            "required": ["schema", "project_id", "ending_id", "actions"],
        },
    }


def execute_ending_plan_tool(request: Mapping[str, Any], *,
                             authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves ending plan requires operator authorization")
    if (type(request) is not dict
            or set(request) - {"schema", "project_id", "ending_id",
                               "actions", "preferred_choices"}
            or not {"schema", "project_id", "ending_id", "actions"}.issubset(request)
            or request.get("schema") != ENDING_PLAN_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves ending plan request")
    from skeleton.ai.game_builder.studio_ecosystem_ending_plan import plan_authored_ending
    from skeleton.ai.game_builder.studio_ecosystem_quest import replay_quest
    if ("preferred_choices" in request
            and type(request["preferred_choices"]) is not dict):
        raise StudioQuestError("invalid typed Jeeves preferred ending choices")
    source = read_blueprint(request["project_id"])
    session = replay_quest(source, request["actions"], authorized=True)
    detail = plan_authored_ending(
        source, ending_id=request["ending_id"], session=session,
        preferred_choices=request.get("preferred_choices"), authorized=True)
    result = {
        "schema": ENDING_PLAN_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result

FACTION_REPUTATION_REQUEST_SCHEMA = "skeleton.jeeves.studio_faction_reputation_request.v1"
FACTION_REPUTATION_RESULT_SCHEMA = "skeleton.jeeves.studio_faction_reputation_result.v1"


def faction_reputation_tool_schema() -> dict[str, object]:
    """Typed operator-gated original faction consequence simulator."""
    return {
        "name": "studio_faction_reputation",
        "description": "Replay authored faction reputation rules without mutating canon",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": FACTION_REPUTATION_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "decisions": {"type": "array", "maxItems": 32,
                              "uniqueItems": True, "items": {"type": "string"}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "decisions"],
        },
    }


def execute_faction_reputation_tool(request: Mapping[str, Any], *,
                                    authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves faction reputation requires operator authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "project_id", "expected_source_digest",
                                "decisions"}
            or request.get("schema") != FACTION_REPUTATION_REQUEST_SCHEMA
            or len(_canonical(request)) > 8192):
        raise StudioQuestError("invalid typed Jeeves faction reputation request")
    from skeleton.ai.game_builder.studio_ecosystem_faction_reputation import (
        simulate_faction_reputation,
    )
    detail = simulate_faction_reputation(
        read_blueprint(request["project_id"]), request["decisions"],
        expected_source_digest=request["expected_source_digest"], authorized=True)
    result = {
        "schema": FACTION_REPUTATION_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result

FACTION_PLAN_REQUEST_SCHEMA = "skeleton.jeeves.studio_faction_plan_request.v1"
FACTION_PLAN_RESULT_SCHEMA = "skeleton.jeeves.studio_faction_plan_result.v1"


def faction_plan_tool_schema() -> dict[str, object]:
    """Operator-gated typed original faction negotiation planner."""
    return {
        "name": "studio_faction_plan",
        "description": "Shortest source-verified original faction reputation plan, no game writes",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": FACTION_PLAN_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "faction_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "minimum": {"type": "integer", "minimum": -100, "maximum": 100},
                "maximum": {"type": "integer", "minimum": -100, "maximum": 100},
                "decisions": {"type": "array", "maxItems": 32,
                              "uniqueItems": True, "items": {"type": "string"}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "faction_id", "decisions"],
        },
    }


def execute_faction_plan_tool(request: Mapping[str, Any], *,
                              authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves faction planning requires operator authorization")
    common = {"schema", "project_id", "expected_source_digest",
              "faction_id", "decisions"}
    optional = {"minimum", "maximum"}
    if (type(request) is not dict or not common.issubset(request)
            or set(request) - common - optional
            or len(set(request) & optional) != 1
            or request.get("schema") != FACTION_PLAN_REQUEST_SCHEMA
            or len(_canonical(request)) > 8192):
        raise StudioQuestError("invalid typed Jeeves faction plan request")
    from skeleton.ai.game_builder.studio_ecosystem_faction_plan import (
        plan_faction_negotiation,
    )
    kwargs = {key: request[key] for key in ("minimum", "maximum")
              if key in request}
    detail = plan_faction_negotiation(
        read_blueprint(request["project_id"]), faction_id=request["faction_id"],
        decisions=request["decisions"],
        expected_source_digest=request["expected_source_digest"],
        authorized=True, **kwargs)
    payload = {
        "schema": FACTION_PLAN_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_STAGING_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_staging_request.v1"
DIALOGUE_STAGING_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_staging_result.v1"


def dialogue_staging_tool_schema() -> dict[str, object]:
    """Discoverable typed scene/NPC dialogue authoring cues, no speech claims."""
    return {
        "name": "studio_dialogue_staging",
        "description": "Source-verified NPC/scene/quest cues and replay-gated editor cards",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_STAGING_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "edits": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "object"}},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_dialogue_staging_tool(request: Mapping[str, Any], *,
                                  authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue staging requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "actions"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"scene_id", "edits"}
            or request.get("schema") != DIALOGUE_STAGING_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue staging request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import (
        compile_dialogue_staging,
    )
    source = read_blueprint(request["project_id"])
    author_receipt = None
    expected = request["expected_source_digest"]
    if "edits" in request:
        from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
            REVISION_SCHEMA, preview_canon_revision,
        )
        source, _, author_receipt = preview_canon_revision(
            source, {
                "schema": REVISION_SCHEMA, "project_id": request["project_id"],
                "expected_source_digest": expected, "edits": request["edits"],
            }, authorized=True)
        expected = author_receipt["revised_source_digest"]
    detail = compile_dialogue_staging(
        source, request["actions"], expected_source_digest=expected,
        scene_id=request.get("scene_id"), authorized=True)
    payload = {
        "schema": DIALOGUE_STAGING_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    if author_receipt is not None:
        payload["author_receipt"] = author_receipt
    payload["result_digest"] = _digest(payload)
    return payload
