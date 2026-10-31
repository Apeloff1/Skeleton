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
    MAX_WALK_EVENTS, MAX_WALK_RECEIPT_BYTES, compare_walk_sessions,
    export_walk_receipt, follow_walk_route, replay_walk,
    restore_walk_receipt, validate_walk_events, walk_branch_forecast,
    walk_checkpoint_timeline, walk_choice_previews, walk_narrative_continuity,
    walk_route_hint,
)

REQUEST_SCHEMA = "skeleton.jeeves.studio_walk_tool_request.v1"
RESULT_SCHEMA = "skeleton.jeeves.studio_walk_tool_result.v1"
OPERATIONS = frozenset({
    "replay", "route", "follow_route", "choices", "forecast", "continuity",
    "timeline", "compare",
})
_ALLOWED = frozenset({"schema", "project_id", "operation", "events", "receipt",
                      "forecast_depth", "compare_events"})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical Jeeves walk tool request") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


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
    validate_walk_events(events)
    depth = request.get("forecast_depth", 2)
    if (type(depth) is not int or not 1 <= depth <= 3
            or ("forecast_depth" in request and operation != "forecast")):
        raise StudioQuestError("invalid Jeeves walk forecast depth")
    comparison = request.get("compare_events")
    if operation == "compare":
        if type(comparison) is not list:
            raise StudioQuestError("compare requires a complete event list")
        validate_walk_events(comparison)
    elif "compare_events" in request:
        raise StudioQuestError("compare_events requires compare operation")
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
    elif operation == "continuity":
        detail = walk_narrative_continuity(session, docs, authorized=True)
    elif operation == "timeline":
        detail = walk_checkpoint_timeline(session, docs, authorized=True)
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
