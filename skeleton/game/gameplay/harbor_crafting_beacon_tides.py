"""Deterministic authored tide hazards over real beacon rescue gameplay.

Tides advance on the canonical world clock. Every player move, craft, repair,
signal and rest is replayed against the same canonical world and beacon report.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest
from .harbor_crafting_beacons import (
    MAX_REPORT_BYTES as MAX_BEACON_REPORT_BYTES, build_beacon_rescue,
    normalize_beacon_action, validate_beacon_board, verify_beacon_rescue,
)

BOARD_SCHEMA = "skeleton.game.harbor.beacon-tides.v1"
REPORT_SCHEMA = "skeleton.game.harbor.beacon-tide-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_BEACON_REPORT_BYTES + 131072
BOARD_FIELDS = {
    "schema", "source_id", "beacon_board_digest", "period", "high_ticks",
    "hazard_tiles", "stamina", "drain", "rest_gain", "rest_at",
}
REPORT_FIELDS = {
    "schema", "source", "beacon_board", "tide_board", "actions",
    "beacon_report", "events", "state", "tide_digest",
}


def _point(value: Any, world: dict[str, Any], label: str) -> list[int]:
    if (not isinstance(value, list) or len(value) != 2
            or any(type(item) is not int for item in value)):
        raise HarborError("invalid " + label)
    x, y = value
    if (not 0 <= y < len(world["map"]) or not 0 <= x < len(world["map"][0])
            or world["map"][y][x] != "."):
        raise HarborError(label + " is not traversable")
    return value


def validate_beacon_tides(board: Any, source: Any, beacon_board: Any) -> dict[str, Any]:
    authored = validate_beacon_board(beacon_board, source)
    _keys(board, BOARD_FIELDS, "beacon tide board")
    if (board["schema"] != BOARD_SCHEMA or board["source_id"] != source["id"]
            or board["beacon_board_digest"] != digest(authored)):
        raise HarborError("beacon tide source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("beacon tide board exceeds byte budget")
    period = _integer(board["period"], 2, 16, "tide period")
    highs = board["high_ticks"]
    if (not isinstance(highs, list) or not 1 <= len(highs) < period
            or any(type(item) is not int or not 0 <= item < period for item in highs)
            or len(set(highs)) != len(highs)):
        raise HarborError("invalid tide high-water phases")
    hazards = board["hazard_tiles"]
    if not isinstance(hazards, list) or not 1 <= len(hazards) <= 16:
        raise HarborError("invalid tide hazard count")
    positions = [tuple(_point(p, source, "tide hazard")) for p in hazards]
    if len(set(positions)) != len(positions):
        raise HarborError("duplicate tide hazard")
    _integer(board["stamina"], 1, 20, "tide stamina")
    _integer(board["drain"], 1, board["stamina"], "tide drain")
    _integer(board["rest_gain"], 1, 20, "tide rest gain")
    shelter = _point(board["rest_at"], source, "tide shelter")
    if tuple(shelter) in positions:
        raise HarborError("tide shelter overlaps hazard")
    return deepcopy(board)


def normalize_tide_action(action: Any) -> dict[str, str]:
    if isinstance(action, dict) and action.get("op") == "rest":
        _keys(action, {"op"}, "tide rest action")
        return {"op": "rest"}
    return normalize_beacon_action(action)


def build_beacon_tide_report(source: Any, beacon_board: Any, tide_board: Any,
                             actions: Any, *, require_rescue: bool = False) -> dict[str, Any]:
    authored = validate_beacon_board(beacon_board, source)
    tide = validate_beacon_tides(tide_board, source, authored)
    if not isinstance(actions, list) or len(actions) > authored["max_turns"]:
        raise HarborError("tide action count exceeds budget")
    normalized: list[dict[str, str]] = []
    core: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    stamina = tide["stamina"]
    failed = False
    previous = digest({"source": digest(source), "tide": digest(tide), "genesis": True})
    beacon_report = build_beacon_rescue(source, authored, [])
    for action in actions:
        if failed or beacon_report["state"]["rescued"]:
            raise HarborError("tide rescue already terminal")
        normalized_action = normalize_tide_action(action)
        mapped = {"op": "wait"} if normalized_action["op"] == "rest" else normalized_action
        advanced = build_beacon_rescue(source, authored, core + [mapped])
        world = advanced["bundle"]["state"]
        tick = world["tick"]
        if normalized_action["op"] == "rest":
            if world["pos"] != tide["rest_at"]:
                raise HarborError("tide rest requires authored shelter")
            stamina = min(tide["stamina"], stamina + tide["rest_gain"])
        elif (world["pos"] in tide["hazard_tiles"]
              and tick % tide["period"] in tide["high_ticks"]):
            stamina = max(0, stamina - tide["drain"])
            if stamina == 0:
                failed = True
        event = {
            "sequence": len(events), "action": normalized_action,
            "beacon_report_digest": advanced["report_digest"],
            "stamina": stamina, "failed": failed, "previous": previous,
        }
        event["digest"] = digest(event)
        events.append(event)
        previous = event["digest"]
        normalized.append(normalized_action)
        core.append(mapped)
        beacon_report = advanced
    rescued = beacon_report["state"]["rescued"] and not failed
    if require_rescue and not rescued:
        raise HarborError("tide rescue not earned")
    report = {
        "schema": REPORT_SCHEMA, "source": deepcopy(source),
        "beacon_board": authored, "tide_board": tide,
        "actions": normalized, "beacon_report": beacon_report,
        "events": events,
        "state": {
            "stamina": stamina, "failed": failed, "rescued": rescued,
            "tick": beacon_report["bundle"]["state"]["tick"],
        },
    }
    report["tide_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("beacon tide report exceeds byte budget")
    return report


def verify_beacon_tide_report(report: Any, *,
                              require_rescue: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "beacon tide report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized tide report")
    if report["tide_digest"] != digest({
        key: value for key, value in report.items() if key != "tide_digest"
    }):
        raise HarborError("beacon tide report digest mismatch")
    verify_beacon_rescue(report["beacon_report"])
    rebuilt = build_beacon_tide_report(
        report["source"], report["beacon_board"], report["tide_board"],
        report["actions"], require_rescue=require_rescue,
    )
    if rebuilt != report:
        raise HarborError("beacon tide replay mismatch")
    return {
        "verified": True, "rescued": rebuilt["state"]["rescued"],
        "failed": rebuilt["state"]["failed"], "stamina": rebuilt["state"]["stamina"],
        "tick": rebuilt["state"]["tick"], "tide_digest": rebuilt["tide_digest"],
    }


def resume_beacon_tide_report(report: Any, actions: Any, *,
                              expected_digest: str,
                              require_rescue: bool = False) -> dict[str, Any]:
    verify_beacon_tide_report(report)
    if type(expected_digest) is not str or expected_digest != report["tide_digest"]:
        raise HarborError("stale beacon tide lease")
    if report["state"]["rescued"] or report["state"]["failed"]:
        raise HarborError("beacon tide already terminal")
    if not isinstance(actions, list):
        raise HarborError("invalid beacon tide continuation")
    return build_beacon_tide_report(
        report["source"], report["beacon_board"], report["tide_board"],
        report["actions"] + actions, require_rescue=require_rescue,
    )
