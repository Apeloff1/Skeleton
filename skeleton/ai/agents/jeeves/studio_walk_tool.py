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

DIALOGUE_PREVIEW_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_preview_request.v1"
DIALOGUE_PREVIEW_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_preview_result.v1"


def dialogue_preview_tool_schema() -> dict[str, object]:
    """Typed source-leased editor choice previews; no fabricated NPC speech."""
    return {
        "name": "studio_dialogue_choice_preview",
        "description": "Preview deterministic authored NPC quest alternatives without committing a choice",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_PREVIEW_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "edits": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "object"}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_dialogue_preview_tool(request: Mapping[str, Any], *,
                                  authorized: bool = False) -> dict[str, Any]:
    """Preview persisted/revised authored scenes through the canonical quest engine."""
    if authorized is not True:
        raise PermissionError("Jeeves dialogue preview requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "actions"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"scene_id", "edits"}
            or request.get("schema") != DIALOGUE_PREVIEW_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or len(request["project_id"]) > 128
            or not request["project_id"]
            or type(request.get("expected_source_digest")) is not str
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue preview request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
        preview_dialogue_choices,
    )
    source = read_blueprint(request["project_id"])
    expected = request["expected_source_digest"]
    author_receipt = None
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
    detail = preview_dialogue_choices(
        source, request["actions"], scene_id=request.get("scene_id"),
        expected_source_digest=expected, authorized=True)
    payload: dict[str, Any] = {
        "schema": DIALOGUE_PREVIEW_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    if author_receipt is not None:
        payload["author_receipt"] = author_receipt
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_COMMIT_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_commit_request.v1"
DIALOGUE_COMMIT_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_commit_result.v1"


def dialogue_commit_tool_schema() -> dict[str, object]:
    """Typed optimistic commit of one previewed authored quest decision."""
    return {
        "name": "studio_dialogue_choice_commit",
        "description": "Replay an exact source-leased NPC choice and return a verified quest save receipt",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_COMMIT_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_preview_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "stage_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "alternative": {"type": "string", "minLength": 1, "maxLength": 256},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "edits": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "object"}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "expected_preview_digest", "stage_id", "alternative", "actions"],
        },
    }


def execute_dialogue_commit_tool(request: Mapping[str, Any], *,
                                 authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue choice commit requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest",
                "expected_preview_digest", "stage_id", "alternative", "actions"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"scene_id", "edits"}
            or request.get("schema") != DIALOGUE_COMMIT_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue choice commit request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_commit import (
        commit_dialogue_choice,
    )
    source = read_blueprint(request["project_id"])
    expected = request["expected_source_digest"]
    author_receipt = None
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
    detail = commit_dialogue_choice(
        source, request["actions"], authorized=True,
        stage_id=request["stage_id"], alternative=request["alternative"],
        expected_preview_digest=request["expected_preview_digest"],
        expected_source_digest=expected, scene_id=request.get("scene_id"))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_COMMIT_RESULT_SCHEMA,
        "project_id": request["project_id"], "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    if author_receipt is not None:
        payload["author_receipt"] = author_receipt
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_RESTORE_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_restore_request.v1"
DIALOGUE_RESTORE_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_restore_result.v1"


def dialogue_restore_tool_schema() -> dict[str, object]:
    """Typed offline restoration of canonical quest saves and NPC editor state."""
    return {
        "name": "studio_dialogue_quest_restore",
        "description": "Verify source-bound quest receipt and resume original NPC scene cards",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_RESTORE_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "receipt": {"type": "object"},
            },
            "required": ["schema", "project_id", "expected_source_digest", "receipt"],
        },
    }


def execute_dialogue_restore_tool(request: Mapping[str, Any], *,
                                  authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue restore requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "receipt"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"scene_id"}
            or request.get("schema") != DIALOGUE_RESTORE_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue restore request")
    from skeleton.ai.game_builder.studio_ecosystem_quest_receipt_restore import (
        restore_quest_receipt,
    )
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import (
        compile_dialogue_staging,
    )
    from skeleton.ai.game_builder.studio_ecosystem_quest import quest_progress
    source = read_blueprint(request["project_id"])
    restored = restore_quest_receipt(
        source, _canonical(request["receipt"]), authorized=True,
        expected_source_digest=request["expected_source_digest"])
    staged = compile_dialogue_staging(
        source, [list(pair) for pair in restored.choices], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        scene_id=request.get("scene_id"))
    detail = {
        "receipt": restored.receipt(), "staging": staged,
        "progress": quest_progress(restored, source),
        "restore_verified": True, "file_write_performed": False,
        "release_certified": False,
    }
    payload = {
        "schema": DIALOGUE_RESTORE_RESULT_SCHEMA,
        "project_id": request["project_id"], "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_TRANSCRIPT_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_transcript_request.v1"
DIALOGUE_TRANSCRIPT_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_transcript_result.v1"


def dialogue_transcript_tool_schema() -> dict[str, object]:
    """Typed authored NPC conversation history with digest-bound pagination."""
    return {
        "name": "studio_dialogue_transcript",
        "description": "Page original NPC scene cues and replayed choices without claiming speech",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_TRANSCRIPT_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "offset": {"type": "integer", "minimum": 0, "maximum": 64},
                "limit": {"type": "integer", "minimum": 1, "maximum": 16},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "edits": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "object"}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_dialogue_transcript_tool(request: Mapping[str, Any], *,
                                     authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue transcript requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "actions"}
    optional = {"scene_id", "offset", "limit", "expected_session_digest", "edits"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - optional
            or request.get("schema") != DIALOGUE_TRANSCRIPT_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue transcript request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_transcript import (
        compile_dialogue_transcript,
    )
    source = read_blueprint(request["project_id"])
    expected = request["expected_source_digest"]
    author_receipt = None
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
    detail = compile_dialogue_transcript(
        source, request["actions"], authorized=True,
        expected_source_digest=expected,
        expected_session_digest=request.get("expected_session_digest"),
        offset=request.get("offset", 0), limit=request.get("limit", 16),
        scene_id=request.get("scene_id"))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_TRANSCRIPT_RESULT_SCHEMA,
        "project_id": request["project_id"], "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    if author_receipt is not None:
        payload["author_receipt"] = author_receipt
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_COMPARE_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_compare_request.v1"
DIALOGUE_COMPARE_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_compare_result.v1"


def dialogue_compare_tool_schema() -> dict[str, object]:
    """Typed comparison of two independently replayed authored NPC branches."""
    return {
        "name": "studio_dialogue_branch_compare",
        "description": "Compare two source-verified original NPC quest histories without changing either",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_COMPARE_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "compare_actions": {"type": "array", "maxItems": 64,
                                    "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                              "items": {"type": "string"}}},
                "edits": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "object"}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "actions", "compare_actions"],
        },
    }


def execute_dialogue_compare_tool(request: Mapping[str, Any], *,
                                  authorized: bool = False) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue comparison requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest",
                "actions", "compare_actions"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"scene_id", "edits"}
            or request.get("schema") != DIALOGUE_COMPARE_REQUEST_SCHEMA
            or len(_canonical(request)) > 32768):
        raise StudioQuestError("invalid typed Jeeves dialogue comparison request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_compare import (
        compare_dialogue_histories,
    )
    source = read_blueprint(request["project_id"])
    expected = request["expected_source_digest"]
    author_receipt = None
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
    detail = compare_dialogue_histories(
        source, request["actions"], request["compare_actions"],
        authorized=True, expected_source_digest=expected,
        scene_id=request.get("scene_id"))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_COMPARE_RESULT_SCHEMA,
        "project_id": request["project_id"], "request_digest": _digest(request),
        "detail": detail, "file_write_performed": False,
        "release_certified": False,
    }
    if author_receipt is not None:
        payload["author_receipt"] = author_receipt
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_FORK_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_fork_request.v1"
DIALOGUE_FORK_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_fork_result.v1"


def dialogue_fork_tool_schema() -> dict[str, object]:
    """Discoverable typed checkpoint replacement; never grants authority."""
    return {
        "name": "studio_dialogue_history_fork",
        "description": "Rewind an original NPC quest history and replay a different authored choice",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_FORK_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "checkpoint_index": {"type": "integer", "minimum": 0, "maximum": 63},
                "alternative": {"type": "string", "minLength": 1, "maxLength": 256},
                "preserve_suffix": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "expected_session_digest", "actions",
                         "checkpoint_index", "alternative"],
        },
    }


def execute_dialogue_fork_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    """Operator-gated Jeeves adapter over canonical replay and branch receipts."""
    if authorized is not True:
        raise PermissionError("Jeeves dialogue fork requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest",
                "expected_session_digest", "actions", "checkpoint_index",
                "alternative"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"preserve_suffix"}
            or request.get("schema") != DIALOGUE_FORK_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue fork request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_fork import (
        fork_dialogue_history,
    )
    source = read_blueprint(request["project_id"])
    detail = fork_dialogue_history(
        source, request["actions"], authorized=True,
        checkpoint_index=request["checkpoint_index"],
        alternative=request["alternative"],
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request["expected_session_digest"],
        preserve_suffix=request.get("preserve_suffix", False))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_FORK_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_CHECKPOINT_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_checkpoint_request.v1"
DIALOGUE_CHECKPOINT_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_checkpoint_result.v1"


def dialogue_checkpoint_tool_schema() -> dict[str, object]:
    """Typed, bounded source-verified checkpoint timeline discovery."""
    return {
        "name": "studio_dialogue_checkpoints",
        "description": "Page original NPC quest replay checkpoints for an exact source/session",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_CHECKPOINT_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "offset": {"type": "integer", "minimum": 0, "maximum": 64},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "expected_session_digest", "actions"],
        },
    }


def execute_dialogue_checkpoint_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue checkpoints require operator authorization")
    required = {"schema", "project_id", "expected_source_digest",
                "expected_session_digest", "actions"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"offset", "limit"}
            or request.get("schema") != DIALOGUE_CHECKPOINT_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue checkpoint request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_checkpoints import (
        page_dialogue_checkpoints,
    )
    source = read_blueprint(request["project_id"])
    detail = page_dialogue_checkpoints(
        source, request["actions"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request["expected_session_digest"],
        offset=request.get("offset", 0), limit=request.get("limit", 8))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_CHECKPOINT_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_ROUTE_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_route_request.v1"
DIALOGUE_ROUTE_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_route_result.v1"


def dialogue_route_tool_schema() -> dict[str, object]:
    """Typed authored NPC scene prerequisite navigation and preview."""
    return {
        "name": "studio_dialogue_scene_route",
        "description": "Plan a replay-verified original quest route to an NPC scene",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_ROUTE_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "target_scene_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "preferred_alternatives": {"type": "object", "maxProperties": 64,
                                           "additionalProperties": {"type": "string"}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "actions", "target_scene_id"],
        },
    }


def execute_dialogue_route_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves dialogue route requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest",
                "actions", "target_scene_id"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"preferred_alternatives"}
            or request.get("schema") != DIALOGUE_ROUTE_REQUEST_SCHEMA
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves dialogue route request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_scene_route import (
        plan_dialogue_scene_route,
    )
    source = read_blueprint(request["project_id"])
    detail = plan_dialogue_scene_route(
        source, request["actions"], authorized=True,
        target_scene_id=request["target_scene_id"],
        expected_source_digest=request["expected_source_digest"],
        preferred_alternatives=request.get("preferred_alternatives"))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_ROUTE_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

DIALOGUE_ITINERARY_REQUEST_SCHEMA = "skeleton.jeeves.studio_dialogue_itinerary_request.v1"
DIALOGUE_ITINERARY_RESULT_SCHEMA = "skeleton.jeeves.studio_dialogue_itinerary_result.v1"


def dialogue_itinerary_tool_schema() -> dict[str, object]:
    """Discoverable source-bound NPC itinerary planner."""
    return {
        "name": "studio_dialogue_itinerary",
        "description": "Plan ordered original NPC scene prerequisites without playing scenes",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": DIALOGUE_ITINERARY_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "target_scene_ids": {"type": "array", "minItems": 1, "maxItems": 8,
                                     "uniqueItems": True,
                                     "items": {"type": "string", "minLength": 1, "maxLength": 512}},
            },
            "required": ["schema", "project_id", "expected_source_digest",
                         "actions", "target_scene_ids"],
        },
    }


def execute_dialogue_itinerary_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC itinerary requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest",
                "actions", "target_scene_ids"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - required - {"expected_session_digest"}
            or request.get("schema") != DIALOGUE_ITINERARY_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves NPC itinerary request")
    from skeleton.ai.game_builder.studio_ecosystem_dialogue_itinerary import (
        plan_dialogue_itinerary,
    )
    detail = plan_dialogue_itinerary(
        read_blueprint(request["project_id"]), request["actions"],
        target_scene_ids=request["target_scene_ids"], authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request.get("expected_session_digest"))
    payload: dict[str, Any] = {
        "schema": DIALOGUE_ITINERARY_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

NPC_CODEX_REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_codex_request.v1"
NPC_CODEX_RESULT_SCHEMA = "skeleton.jeeves.studio_npc_codex_result.v1"


def npc_codex_tool_schema() -> dict[str, object]:
    """Read-only original NPC encounter index with exact continuation leases."""
    return {
        "name": "studio_npc_encounter_codex",
        "description": "Page source-verified original NPC encounter cues and quest status",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": NPC_CODEX_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "npc_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 16},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_npc_codex_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves NPC codex requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "actions"}
    allowed = required | {"expected_session_digest", "npc_id", "offset", "limit"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - allowed or request.get("schema") != NPC_CODEX_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves NPC codex request")
    from skeleton.ai.game_builder.studio_ecosystem_npc_codex import page_npc_encounters
    detail = page_npc_encounters(
        read_blueprint(request["project_id"]), request["actions"],
        authorized=True, expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request.get("expected_session_digest"),
        npc_id=request.get("npc_id"), offset=request.get("offset", 0),
        limit=request.get("limit", 8))
    payload: dict[str, Any] = {
        "schema": NPC_CODEX_RESULT_SCHEMA, "project_id": request["project_id"],
        "request_digest": _digest(request), "detail": detail,
        "file_write_performed": False, "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

NPC_CONTINUITY_REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_continuity_request.v1"
NPC_CONTINUITY_RESULT_SCHEMA = "skeleton.jeeves.studio_npc_continuity_result.v1"


def npc_continuity_tool_schema() -> dict[str, object]:
    """Typed read-only NPC chronology and causal proof; authorization out of band."""
    return {
        "name": "studio_npc_scene_continuity",
        "description": "Audit original NPC chronology and quest dependencies without playing scenes",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": NPC_CONTINUITY_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
                "npc_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "require_chronological_prerequisites": {"type": "boolean"},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_npc_continuity_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    """Bind a typed Jeeves request to the authoritative source and quest replay."""
    if authorized is not True:
        raise PermissionError("Jeeves NPC continuity requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "actions"}
    allowed = required | {
        "expected_session_digest", "npc_id",
        "require_chronological_prerequisites",
    }
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - allowed
            or request.get("schema") != NPC_CONTINUITY_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves NPC continuity request")
    from skeleton.ai.game_builder.studio_ecosystem_npc_continuity import (
        audit_npc_continuity,
    )
    detail = audit_npc_continuity(
        read_blueprint(request["project_id"]), request["actions"],
        authorized=True, expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request.get("expected_session_digest"),
        npc_id=request.get("npc_id"),
        require_chronological_prerequisites=request.get(
            "require_chronological_prerequisites", False),
    )
    payload: dict[str, Any] = {
        "schema": NPC_CONTINUITY_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

NPC_AUTHOR_REQUEST_SCHEMA = "skeleton.jeeves.studio_npc_author_request.v1"
NPC_AUTHOR_RESULT_SCHEMA = "skeleton.jeeves.studio_npc_author_result.v1"


def npc_author_tool_schema() -> dict[str, object]:
    """Typed NPC prose authoring through the existing verified revision compiler."""
    return {
        "name": "studio_npc_persona_author",
        "description": "Preview an original NPC prose edit and source-bound playable HTML",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": NPC_AUTHOR_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "npc_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "changes": {"type": "object", "minProperties": 1, "maxProperties": 3,
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "minLength": 1, "maxLength": 512},
                                "knows": {"type": "string", "minLength": 1, "maxLength": 512},
                                "relationship": {"type": "string", "minLength": 1, "maxLength": 512},
                            }},
            },
            "required": ["schema", "project_id", "npc_id",
                         "expected_source_digest", "changes"],
        },
    }


def execute_npc_author_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    """No filesystem write: operator chooses private persistence separately."""
    if authorized is not True:
        raise PermissionError("Jeeves NPC authoring requires operator authorization")
    required = {"schema", "project_id", "npc_id",
                "expected_source_digest", "changes"}
    if (type(request) is not dict or set(request) != required
            or request.get("schema") != NPC_AUTHOR_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 8192):
        raise StudioQuestError("invalid typed Jeeves NPC authoring request")
    from skeleton.ai.game_builder.studio_ecosystem_npc_persona_author import (
        preview_npc_persona_revision,
    )
    _, _, _, detail = preview_npc_persona_revision(
        read_blueprint(request["project_id"]),
        npc_id=request["npc_id"], changes=request["changes"],
        expected_source_digest=request["expected_source_digest"],
        authorized=True)
    payload: dict[str, Any] = {
        "schema": NPC_AUTHOR_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

CHOICE_AUTHOR_REQUEST_SCHEMA = "skeleton.jeeves.studio_quest_choice_author_request.v1"
CHOICE_AUTHOR_RESULT_SCHEMA = "skeleton.jeeves.studio_quest_choice_author_result.v1"


def choice_author_tool_schema() -> dict[str, object]:
    """Typed original quest prose edit and canonical replay preview."""
    return {
        "name": "studio_quest_choice_author",
        "description": "Edit an original quest alternative and verify playable branch replay",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": CHOICE_AUTHOR_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "stage_id": {"type": "string", "minLength": 1, "maxLength": 512},
                "alternative_index": {"type": "integer", "minimum": 0, "maximum": 7},
                "replacement": {"type": "string", "minLength": 1, "maxLength": 512},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_alternative_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": ["schema", "project_id", "stage_id", "alternative_index",
                         "replacement", "expected_source_digest",
                         "expected_alternative_digest"],
        },
    }


def execute_choice_author_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves quest choice authoring requires operator authorization")
    required = {"schema", "project_id", "stage_id", "alternative_index",
                "replacement", "expected_source_digest", "expected_alternative_digest"}
    if (type(request) is not dict or set(request) != required
            or request.get("schema") != CHOICE_AUTHOR_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 8192):
        raise StudioQuestError("invalid typed Jeeves quest choice request")
    from skeleton.ai.game_builder.studio_ecosystem_quest_choice_author import (
        preview_quest_choice_revision,
    )
    _, _, _, detail = preview_quest_choice_revision(
        read_blueprint(request["project_id"]),
        stage_id=request["stage_id"],
        alternative_index=request["alternative_index"],
        replacement=request["replacement"],
        expected_source_digest=request["expected_source_digest"],
        expected_alternative_digest=request["expected_alternative_digest"],
        authorized=True)
    payload: dict[str, Any] = {
        "schema": CHOICE_AUTHOR_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload

GUIDED_WALK_REQUEST_SCHEMA = "skeleton.jeeves.studio_guided_walk_request.v1"
GUIDED_WALK_RESULT_SCHEMA = "skeleton.jeeves.studio_guided_walk_result.v1"


def guided_walk_tool_schema() -> dict[str, object]:
    """Typed operator-directed original-world route and choice execution."""
    return {
        "name": "studio_guided_world_walk",
        "description": "Replay guided original-world movement and explicitly authored choices",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": GUIDED_WALK_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "events": {"type": "array", "maxItems": MAX_WALK_EVENTS,
                           "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                     "items": {"type": "string"}}},
                "authored_choices": {"type": "array", "minItems": 1, "maxItems": 3,
                                     "items": {"type": "string", "minLength": 1,
                                               "maxLength": 256}},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": ["schema", "project_id", "events", "authored_choices",
                         "expected_source_digest", "expected_session_digest"],
        },
    }


def execute_guided_walk_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves guided walk requires operator authorization")
    required = {"schema", "project_id", "events", "authored_choices",
                "expected_source_digest", "expected_session_digest"}
    if (type(request) is not dict or set(request) != required
            or request.get("schema") != GUIDED_WALK_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > MAX_WALK_RECEIPT_BYTES):
        raise StudioQuestError("invalid typed Jeeves guided walk request")
    from skeleton.ai.game_builder.studio_ecosystem_guided_walk import (
        execute_guided_walk,
    )
    _, detail = execute_guided_walk(
        read_blueprint(request["project_id"]), request["events"],
        authored_choices=request["authored_choices"],
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request["expected_session_digest"],
        authorized=True)
    payload: dict[str, Any] = {
        "schema": GUIDED_WALK_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload


ENDING_ATLAS_REQUEST_SCHEMA = "skeleton.jeeves.studio_ending_atlas_request.v1"
ENDING_ATLAS_RESULT_SCHEMA = "skeleton.jeeves.studio_ending_atlas_result.v1"


def ending_atlas_tool_schema() -> dict[str, object]:
    """Typed source-leased comparison of all original narrative endings."""
    return {
        "name": "studio_authored_ending_atlas",
        "description": "Compare replayable original ending routes and external evidence holds",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "schema": {"type": "string", "const": ENDING_ATLAS_REQUEST_SCHEMA},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "expected_source_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "expected_session_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "actions": {"type": "array", "maxItems": 64,
                            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                      "items": {"type": "string"}}},
            },
            "required": ["schema", "project_id", "expected_source_digest", "actions"],
        },
    }


def execute_ending_atlas_tool(
    request: Mapping[str, Any], *, authorized: bool = False,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("Jeeves ending atlas requires operator authorization")
    required = {"schema", "project_id", "expected_source_digest", "actions"}
    allowed = required | {"expected_session_digest"}
    if (type(request) is not dict or not required.issubset(request)
            or set(request) - allowed
            or request.get("schema") != ENDING_ATLAS_REQUEST_SCHEMA
            or type(request.get("project_id")) is not str
            or not 1 <= len(request["project_id"]) <= 128
            or len(_canonical(request)) > 16384):
        raise StudioQuestError("invalid typed Jeeves ending atlas request")
    from skeleton.ai.game_builder.studio_ecosystem_ending_atlas import (
        build_ending_atlas,
    )
    detail = build_ending_atlas(
        read_blueprint(request["project_id"]), request["actions"],
        authorized=True,
        expected_source_digest=request["expected_source_digest"],
        expected_session_digest=request.get("expected_session_digest"),
    )
    payload: dict[str, Any] = {
        "schema": ENDING_ATLAS_RESULT_SCHEMA,
        "project_id": request["project_id"],
        "request_digest": _digest(request),
        "detail": detail,
        "file_write_performed": False,
        "release_certified": False,
    }
    payload["result_digest"] = _digest(payload)
    return payload
