"""Deterministic source-leased replay of an original multi-world browser session.

A browser export is untrusted. Recompute every move from reviewed source,
reject fabricated endings, flags, portals and stale network/world digests.
No language-model proposal may authorize a saved session.
"""
from __future__ import annotations

from typing import Any

from .portals import validate_network
from .world_canon import (
    CanonError, _flags, _id, _keys, _list, canonical, digest, strict_json,
)

SCHEMA = "jeeves.world.portal_session.v1"
REPORT_SCHEMA = "jeeves.world.portal_session_proof.v1"
STORED_SCHEMA = "jeeves.world.portal_session_record.v1"
MAX_MOVES = 256


def replay_session(session: Any, network: Any,
                   worlds: dict[str, Any]) -> dict[str, Any]:
    """Verify a complete browser trace against exactly the reviewed source."""
    validate_network(network, worlds)
    if network["approved"] is not True:
        raise CanonError("portals_review_required")
    data = _keys(session, {
        "schema", "network_id", "network_digest", "world_digests",
        "steps", "current_world", "current_scene", "flags",
    })
    if data["schema"] != SCHEMA:
        raise CanonError("portal_session_schema_mismatch")
    if data["network_id"] != network["id"] or (
        data["network_digest"] != digest(network)
    ) or data["world_digests"] != network["world_digests"]:
        raise CanonError("portal_session_source_lease_mismatch")
    steps = _list(data["steps"], "steps", MAX_MOVES)
    if len(canonical(data)) > 524288:
        raise CanonError("portal_session_too_large")
    world_id = network["root_world"]
    scene_id = worlds[world_id]["start"]
    flags: dict[str, set[str]] = {wid: set() for wid in worlds}
    witnesses: list[dict[str, str]] = []
    for index, item in enumerate(steps):
        step = _keys(item, {"kind", "world", "id"})
        kind = step["kind"]
        wid = _id(step["world"], "step.world")
        sid = _id(step["id"], "step.id")
        if wid != world_id:
            raise CanonError("portal_session_wrong_world", str(index))
        world = worlds[world_id]
        if kind == "choice":
            if any(e["scene"] == scene_id for e in world["endings"]):
                raise CanonError("portal_session_choice_after_ending", str(index))
            matches = [c for c in world["choices"] if c["id"] == sid]
            if len(matches) != 1 or matches[0]["from"] != scene_id:
                raise CanonError("portal_session_invalid_choice", str(index))
            choice = matches[0]
            if not set(choice["requires"]) <= flags[world_id]:
                raise CanonError("portal_session_unearned_choice", str(index))
            flags[world_id].update(choice["grants"])
            scene_id = choice["to"]
        elif kind == "portal":
            if not any(e["scene"] == scene_id for e in world["endings"]):
                raise CanonError("portal_session_portal_before_ending", str(index))
            matches = [p for p in network["portals"] if p["id"] == sid]
            if len(matches) != 1 or matches[0]["from_world"] != world_id or (
                matches[0]["from_ending"] != scene_id
            ):
                raise CanonError("portal_session_invalid_portal", str(index))
            world_id = matches[0]["to_world"]
            scene_id = worlds[world_id]["start"]
        else:
            raise CanonError("portal_session_invalid_step_kind", str(index))
        witnesses.append({"kind": kind, "world": wid, "id": sid})
    if _id(data["current_world"], "current_world") != world_id or (
        _id(data["current_scene"], "current_scene") != scene_id
    ):
        raise CanonError("portal_session_forged_position")
    observed_flags = _keys(data["flags"], set(worlds))
    for wid in sorted(worlds):
        declared = _flags(observed_flags[wid], "session.flags")
        if declared != sorted(flags[wid]):
            raise CanonError("portal_session_forged_flags", wid)
    result = {
        "schema": REPORT_SCHEMA, "network_id": network["id"],
        "network_digest": digest(network),
        "world_digests": network["world_digests"],
        "session_digest": digest(data), "moves": len(steps),
        "current_world": world_id, "current_scene": scene_id,
        "flags": {wid: sorted(flags[wid]) for wid in sorted(worlds)},
        "ending_reached": any(
            e["scene"] == scene_id for e in worlds[world_id]["endings"]
        ),
        "witnesses": witnesses,
        "qualification": "source_verified_offline_trace_not_device_certified",
    }
    strict_json(canonical(result))
    return result
