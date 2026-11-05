"""Deterministic original-game acceptance bound to a full playable rescue."""
from __future__ import annotations

from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_beacon_package import verify_beacon_package_play

SCHEMA = "skeleton.game.harbor.beacon-acceptance.v1"
MAX_ACCEPTANCE_BYTES = 32768
FIELDS = {
    "schema", "source_digest", "board_digest", "package_digest",
    "play_digest", "proof", "acceptance_digest",
}
PROOF_FIELDS = {
    "world", "ordered_signals", "ticks", "rescue_score", "delivered",
    "ending", "event_tip", "canonical_tip", "rescued",
}


def accept_beacon_play(play: Any) -> dict[str, Any]:
    verify_beacon_package_play(play, require_rescue=True)
    package = play["package"]
    report = play["report"]
    world = package["source"]
    board = package["board"]
    state = report["state"]
    canonical_state = report["bundle"]["state"]
    if (not state["rescued"] or not canonical_state["delivered"]
            or canonical_state["ending"] != "beacon"):
        raise HarborError("beacon original-game acceptance not earned")
    if (len(state["signaled"]) != len(board["beacons"])
            or set(state["signaled"]) != {item["id"] for item in board["beacons"]}):
        raise HarborError("beacon original-game signal set invalid")
    if not report["events"]:
        raise HarborError("beacon original-game event chain missing")
    proof = {
        "world": world["id"],
        "ordered_signals": list(state["signaled"]),
        "ticks": state["tick"],
        "rescue_score": max(0, board["max_turns"] - state["tick"])
                        + 10 * len(state["signaled"]),
        "delivered": canonical_state["delivered"],
        "ending": canonical_state["ending"],
        "event_tip": report["events"][-1]["digest"],
        "canonical_tip": report["bundle"]["terminal_digest"],
        "rescued": state["rescued"],
    }
    certificate = {
        "schema": SCHEMA, "source_digest": report["source_digest"],
        "board_digest": report["board_digest"],
        "package_digest": package["package_digest"],
        "play_digest": play["play_digest"], "proof": proof,
    }
    certificate["acceptance_digest"] = digest(certificate)
    if len(canonical(certificate)) > MAX_ACCEPTANCE_BYTES:
        raise HarborError("beacon acceptance exceeds byte budget")
    return certificate


def verify_beacon_acceptance(play: Any, certificate: Any) -> dict[str, Any]:
    _keys(certificate, FIELDS, "beacon acceptance")
    if certificate["schema"] != SCHEMA or len(canonical(certificate)) > MAX_ACCEPTANCE_BYTES:
        raise HarborError("unsupported or oversized beacon acceptance")
    _keys(certificate["proof"], PROOF_FIELDS, "beacon acceptance proof")
    if certificate["acceptance_digest"] != digest({
        key: value for key, value in certificate.items() if key != "acceptance_digest"
    }):
        raise HarborError("beacon acceptance digest mismatch")
    rebuilt = accept_beacon_play(play)
    if rebuilt != certificate:
        raise HarborError("beacon acceptance replay mismatch")
    return {
        "verified": True, "rescued": True,
        "score": rebuilt["proof"]["rescue_score"],
        "acceptance_digest": rebuilt["acceptance_digest"],
        "play_digest": rebuilt["play_digest"],
    }
