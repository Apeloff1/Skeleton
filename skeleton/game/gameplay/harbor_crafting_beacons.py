"""Original source-bound beacon rescue: movement, crafting, signals and replay.

All inventory and NPC collision rules come from the canonical harbor engine.
Beacon interactions consume real world ticks. A repair requires an earned,
reusable crafted tool; rescue requires a real dock delivery and signal ending.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, normalize_action,
    step, validate_source, verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.beacon-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.beacon-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 4
MAX_BEACONS = 12
BOARD_FIELDS = {"schema", "source_id", "beacons", "repair_tool", "max_turns"}
BEACON_FIELDS = {"id", "at", "power", "requires"}
REPORT_FIELDS = {
    "schema", "source", "board", "actions", "bundle", "events",
    "state", "source_digest", "board_digest", "report_digest",
}
SPECIAL = {"repair", "signal", "rescue"}


def _distance(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def validate_beacon_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_FIELDS, "beacon board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("beacon board source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("beacon board exceeds byte budget")
    _integer(board["max_turns"], 1, world["max_ticks"], "beacon turn budget")
    tool = _identifier(board["repair_tool"], "beacon repair tool")
    if tool not in {
        item for recipe in world["recipes"] for item in recipe["output"]
    }:
        raise HarborError("beacon tool must be craftable from canonical source")
    beacons = board["beacons"]
    if not isinstance(beacons, list) or not 1 <= len(beacons) <= MAX_BEACONS:
        raise HarborError("invalid beacon count")
    seen: set[str] = set()
    occupied: set[tuple[int, int]] = set()
    for beacon in beacons:
        _keys(beacon, BEACON_FIELDS, "beacon")
        name = _identifier(beacon["id"], "beacon id")
        if name in seen:
            raise HarborError("duplicate beacon id")
        pos = beacon["at"]
        if (not isinstance(pos, list) or len(pos) != 2
                or any(type(value) is not int for value in pos)):
            raise HarborError("invalid beacon position")
        x, y = pos
        if (not 0 <= y < len(world["map"])
                or not 0 <= x < len(world["map"][0])
                or world["map"][y][x] != "."):
            raise HarborError("beacon is on blocked tile")
        if tuple(pos) in occupied or pos in world["npc"]["route"] or pos == world["dock"]:
            raise HarborError("beacon overlaps another entity")
        _integer(beacon["power"], 1, 4, "beacon power")
        requires = beacon["requires"]
        if (not isinstance(requires, list) or len(requires) > MAX_BEACONS
                or any(type(item) is not str or item not in seen for item in requires)
                or len(set(requires)) != len(requires)):
            raise HarborError("beacon prerequisites must reference earlier unique signals")
        seen.add(name)
        occupied.add(tuple(pos))
    return deepcopy(board)


def normalize_beacon_action(action: Any) -> dict[str, str]:
    if not isinstance(action, dict) or type(action.get("op")) is not str:
        raise HarborError("invalid beacon action")
    op = action["op"]
    if op in {"repair", "signal"}:
        _keys(action, {"op", "beacon"}, "beacon action")
        return {"op": op, "beacon": _identifier(action["beacon"], "beacon target")}
    if op == "rescue":
        _keys(action, {"op"}, "rescue action")
        return {"op": "rescue"}
    if op == "choose":
        raise HarborError("direct choice bypasses beacon rescue")
    return normalize_action(action)


def _initial(board: dict[str, Any]) -> dict[str, Any]:
    return {
        "repaired": {beacon["id"]: 0 for beacon in board["beacons"]},
        "signaled": [],
        "rescued": False,
        "tick": 0,
    }


def _transition(board: dict[str, Any], overlay: dict[str, Any],
                before: dict[str, Any], after: dict[str, Any],
                action: dict[str, str]) -> dict[str, Any]:
    if overlay["rescued"]:
        raise HarborError("beacon rescue already terminal")
    updated = deepcopy(overlay)
    op = action["op"]
    if op in {"repair", "signal"}:
        beacon = next((b for b in board["beacons"] if b["id"] == action["beacon"]), None)
        if beacon is None:
            raise HarborError("unknown beacon target")
        if _distance(after["pos"], beacon["at"]) > 1:
            raise HarborError("beacon out of reach")
        name = beacon["id"]
        if name in updated["signaled"]:
            raise HarborError("beacon already signaled")
        if op == "repair":
            if after["inventory"].get(board["repair_tool"], 0) < 1:
                raise HarborError("beacon repair tool not earned")
            if updated["repaired"][name] >= beacon["power"]:
                raise HarborError("beacon already fully repaired")
            updated["repaired"][name] += 1
        else:
            if updated["repaired"][name] != beacon["power"]:
                raise HarborError("beacon power not earned")
            if not set(beacon["requires"]).issubset(updated["signaled"]):
                raise HarborError("beacon prerequisite signal missing")
            updated["signaled"].append(name)
    elif op == "rescue":
        if (len(updated["signaled"]) != len(board["beacons"])
                or not before["delivered"] or after["ending"] != "beacon"):
            raise HarborError("beacon rescue not earned")
        updated["rescued"] = True
    updated["tick"] += 1
    if updated["tick"] > board["max_turns"]:
        raise HarborError("beacon authored turn budget exhausted")
    return updated


def build_beacon_rescue(source: Any, board: Any, actions: Any, *,
                        require_rescue: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_beacon_board(board, world)
    if not isinstance(actions, list) or len(actions) > authored["max_turns"]:
        raise HarborError("beacon action count exceeds budget")
    state = initial_state(world)
    overlay = _initial(authored)
    core_actions: list[dict[str, str]] = []
    normalized: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    previous = digest({"source": digest(world), "board": digest(authored), "genesis": True})
    for value in actions:
        action = normalize_beacon_action(value)
        op = action["op"]
        canonical_action = (
            {"op": "choose", "choice": "signal"} if op == "rescue"
            else {"op": "wait"} if op in {"repair", "signal"}
            else action
        )
        before_overlay = digest(overlay)
        next_world = step(world, state, canonical_action)
        next_overlay = _transition(authored, overlay, state, next_world, action)
        event = {
            "sequence": len(events), "action": action, "before": before_overlay,
            "after": digest(next_overlay), "world_after": digest(next_world),
            "previous": previous,
        }
        event["digest"] = digest(event)
        events.append(event)
        previous = event["digest"]
        state, overlay = next_world, next_overlay
        normalized.append(action)
        core_actions.append(canonical_action)
    if require_rescue and not overlay["rescued"]:
        raise HarborError("beacon rescue not earned")
    bundle = export_bundle(world, core_actions)
    if bundle["state"] != state:
        raise HarborError("beacon and canonical world replay diverged")
    report = {
        "schema": REPORT_SCHEMA, "source": world, "board": authored,
        "actions": normalized, "bundle": bundle, "events": events,
        "state": overlay, "source_digest": digest(world),
        "board_digest": digest(authored),
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("beacon report exceeds byte budget")
    return report


def verify_beacon_rescue(report: Any, *, require_rescue: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "beacon report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized beacon report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("beacon report digest mismatch")
    verify_bundle(report["bundle"])
    rebuilt = build_beacon_rescue(
        report["source"], report["board"], report["actions"],
        require_rescue=require_rescue,
    )
    if rebuilt != report:
        raise HarborError("beacon replay mismatch")
    return _beacon_status(rebuilt)


def beacon_status(report: Any) -> dict[str, Any]:
    """Return only independently replay-verified beacon status."""
    return verify_beacon_rescue(report)


def _beacon_status(report: dict[str, Any]) -> dict[str, Any]:
    verify = report["state"]
    return {
        "rescued": verify["rescued"],
        "signaled": list(verify["signaled"]),
        "repaired": dict(verify["repaired"]),
        "tick": verify["tick"],
        "position": list(report["bundle"]["state"]["pos"]),
        "delivered": report["bundle"]["state"]["delivered"],
        "report_digest": report["report_digest"],
    }


def resume_beacon_rescue(report: Any, actions: Any, *, expected_digest: str,
                         require_rescue: bool = False) -> dict[str, Any]:
    verify_beacon_rescue(report)
    if type(expected_digest) is not str or expected_digest != report["report_digest"]:
        raise HarborError("stale beacon rescue lease")
    if report["state"]["rescued"]:
        raise HarborError("beacon rescue already terminal")
    if not isinstance(actions, list):
        raise HarborError("invalid beacon continuation")
    return build_beacon_rescue(
        report["source"], report["board"], report["actions"] + actions,
        require_rescue=require_rescue,
    )
