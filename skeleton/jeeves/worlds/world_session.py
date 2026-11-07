"""Bounded deterministic session replay for reviewed canonical playable worlds.

This is a pure replay contract, not a storage authorization or a substitute for
WorldStore's revision lease. Sessions bind to a canonical source digest so edits
cannot silently reinterpret a player's previous choices.
"""
from __future__ import annotations

from typing import Any

from skeleton.jeeves.worlds.world_canon import (
    CanonError, MAX_CHOICES, _id, _keys, canonical, digest, prove, validate,
)

SESSION_SCHEMA = "jeeves.world.session.v1"


def replay(source: Any, choice_ids: Any) -> dict[str, Any]:
    """Replay a bounded ordered choice trace against the exact canonical world."""
    world = validate(source)
    proof = prove(world)
    if type(choice_ids) is not list or len(choice_ids) > MAX_CHOICES:
        raise CanonError("invalid_session_trace")
    by_id = {choice["id"]: choice for choice in world["choices"]}
    endings = {ending["scene"] for ending in world["endings"]}
    scene = world["start"]
    flags: set[str] = set()
    trace: list[str] = []
    for index, raw_id in enumerate(choice_ids):
        choice_id = _id(raw_id, "session.choice")
        choice = by_id.get(choice_id)
        if choice is None:
            raise CanonError("unknown_session_choice", str(index))
        if scene in endings:
            raise CanonError("session_after_ending", str(index))
        if choice["from"] != scene:
            raise CanonError("session_wrong_scene", str(index))
        if not set(choice["requires"]).issubset(flags):
            raise CanonError("session_requirements_unmet", str(index))
        flags.update(choice["grants"])
        scene = choice["to"]
        trace.append(choice_id)
    return {
        "schema": SESSION_SCHEMA,
        "source_digest": proof.source_digest,
        "scene": scene,
        "flags": sorted(flags),
        "trace": trace,
        "ended": scene in endings,
    }


def restore(source: Any, receipt: Any) -> dict[str, Any]:
    """Reject tampering, stale source, impossible state, and extra fields."""
    item = _keys(receipt, {
        "schema", "source_digest", "scene", "flags", "trace", "ended",
    })
    if item["schema"] != SESSION_SCHEMA:
        raise CanonError("session_schema_mismatch")
    world = validate(source)
    if item["source_digest"] != digest(world):
        raise CanonError("session_stale_source")
    expected = replay(world, item["trace"])
    if canonical(item) != canonical(expected):
        raise CanonError("session_state_mismatch")
    return expected


MAX_RECEIPT_BYTES = 65536


def export_json(source: Any, choice_ids: Any) -> bytes:
    """Export a portable, bounded receipt without persisting unreviewed state."""
    payload = canonical(replay(source, choice_ids))
    if len(payload) > MAX_RECEIPT_BYTES:
        raise CanonError("session_too_large")
    return payload


def restore_json(source: Any, payload: Any) -> dict[str, Any]:
    """Parse an untrusted portable receipt with duplicate-key and size checks.

    The browser and Python runtimes use the same receipt schema.  UTF-8 byte
    bounds are applied before JSON decoding to prevent oversized allocations.
    """
    from skeleton.jeeves.worlds.world_canon import strict_json

    if type(payload) is not bytes:
        raise CanonError("invalid_session_payload")
    if len(payload) > MAX_RECEIPT_BYTES:
        raise CanonError("session_too_large")
    return restore(source, strict_json(payload))
