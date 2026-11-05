"""Playable source-bound salvage: finite recovery, storms, dock delivery and replay.

The canonical Lantern Quay engine alone owns movement, crafting, inventory and
NPC collision. Salvage is an additional deterministic finite-state mission.
No overlay action mints canonical items or bypasses the earned ending.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, normalize_action,
    step, validate_source, verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.salvage-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.salvage-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 4
MAX_SITES = 16
BOARD_KEYS = {"schema", "source_id", "sites", "tool", "max_turns", "hull", "cargo_capacity", "tide_period"}
SITE_KEYS = {"id", "at", "weight", "reward"}
REPORT_KEYS = {"schema", "source", "board", "actions", "bundle", "events", "state",
               "source_digest", "board_digest", "report_digest"}
SPECIAL = {"salvage", "offload", "patch", "rescue"}


def distance(left: list[int], right: list[int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def validate_salvage_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_KEYS, "salvage board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("salvage source identity mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("salvage board exceeds byte budget")
    _integer(board["max_turns"], 1, world["max_ticks"], "salvage turn budget")
    _integer(board["hull"], 1, 12, "salvage hull")
    _integer(board["cargo_capacity"], 1, 32, "salvage cargo capacity")
    _integer(board["tide_period"], 2, 32, "salvage tide period")
    tool = _identifier(board["tool"], "salvage patch tool")
    if tool not in {item for recipe in world["recipes"] for item in recipe["output"]}:
        raise HarborError("salvage patch tool must be craftable")
    sites = board["sites"]
    if not isinstance(sites, list) or not 1 <= len(sites) <= MAX_SITES:
        raise HarborError("invalid salvage site count")
    names: set[str] = set()
    positions: set[tuple[int, int]] = set()
    for site in sites:
        _keys(site, SITE_KEYS, "salvage site")
        name = _identifier(site["id"], "salvage site id")
        pos = site["at"]
        if (not isinstance(pos, list) or len(pos) != 2
                or any(type(v) is not int for v in pos)):
            raise HarborError("invalid salvage site position")
        x, y = pos
        if (not 0 <= y < len(world["map"]) or not 0 <= x < len(world["map"][0])
                or world["map"][y][x] != "."):
            raise HarborError("salvage site on blocked tile")
        if (name in names or tuple(pos) in positions or pos in world["npc"]["route"]
                or pos == world["dock"] or pos == world["start"]):
            raise HarborError("duplicate or occupied salvage site")
        _integer(site["weight"], 1, 8, "salvage cargo weight")
        _integer(site["reward"], 1, 100, "salvage reward")
        if site["weight"] > board["cargo_capacity"]:
            raise HarborError("salvage site exceeds cargo capacity")
        names.add(name)
        positions.add(tuple(pos))
    return deepcopy(board)


def normalize_salvage_action(value: Any) -> dict[str, str]:
    if isinstance(value, dict) and type(value.get("op")) is str:
        if value["op"] == "salvage":
            _keys(value, {"op", "site"}, "salvage action")
            return {"op": "salvage", "site": _identifier(value["site"], "salvage target")}
        if value["op"] in SPECIAL - {"salvage"}:
            _keys(value, {"op"}, "salvage action")
            return {"op": value["op"]}
        if value["op"] == "choose":
            raise HarborError("direct ending bypasses salvage contract")
    return normalize_action(value)


def initial_salvage_state(board: dict[str, Any]) -> dict[str, Any]:
    return {"tick": 0, "hull": board["hull"], "cargo": [],
            "secured": [], "reward": 0, "complete": False, "failed": False}


def _transition(world: dict[str, Any], board: dict[str, Any],
                overlay: dict[str, Any], before: dict[str, Any],
                after: dict[str, Any], action: dict[str, str]) -> dict[str, Any]:
    if overlay["complete"] or overlay["failed"]:
        raise HarborError("salvage mission already terminal")
    updated = deepcopy(overlay)
    op = action["op"]
    if op == "salvage":
        site = next((s for s in board["sites"] if s["id"] == action["site"]), None)
        if site is None:
            raise HarborError("unknown salvage site")
        if site["id"] in updated["cargo"] or site["id"] in updated["secured"]:
            raise HarborError("salvage site already recovered")
        if after["pos"] != site["at"]:
            raise HarborError("salvage requires standing on authored site")
        weight = sum(s["weight"] for s in board["sites"] if s["id"] in updated["cargo"])
        if weight + site["weight"] > board["cargo_capacity"]:
            raise HarborError("salvage cargo capacity exceeded")
        updated["cargo"].append(site["id"])
        if after["tick"] % board["tide_period"] == 0:
            updated["hull"] -= 1
    elif op == "offload":
        if distance(after["pos"], world["dock"]) != 1 or not updated["cargo"]:
            raise HarborError("offload requires cargo at dock")
        updated["secured"].extend(updated["cargo"])
        updated["reward"] += sum(
            site["reward"] for site in board["sites"] if site["id"] in updated["cargo"]
        )
        updated["cargo"] = []
    elif op == "patch":
        if after["inventory"].get(board["tool"], 0) < 1:
            raise HarborError("patch tool not earned through crafting")
        if updated["hull"] >= board["hull"]:
            raise HarborError("hull already intact")
        if not updated["cargo"]:
            raise HarborError("patch requires sacrificing one recovered cargo")
        updated["cargo"].pop()
        updated["hull"] += 1
    elif op == "rescue":
        if (len(updated["secured"]) != len(board["sites"])
                or updated["cargo"] or not before["delivered"]
                or after["ending"] != "beacon"
                or distance(after["pos"], world["dock"]) != 1):
            raise HarborError("salvage rescue ending not earned")
        updated["complete"] = True
    updated["tick"] += 1
    if updated["tick"] > board["max_turns"]:
        raise HarborError("salvage authored turn budget exhausted")
    if updated["hull"] <= 0:
        updated["failed"] = True
    return updated


def build_salvage(source: Any, board: Any, actions: Any, *,
                  require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_salvage_board(board, world)
    if not isinstance(actions, list) or len(actions) > authored["max_turns"]:
        raise HarborError("salvage action count exceeds budget")
    state = initial_state(world)
    overlay = initial_salvage_state(authored)
    core_actions: list[dict[str, str]] = []
    normalized: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    previous = digest({"source": digest(world), "board": digest(authored), "genesis": True})
    for raw in actions:
        action = normalize_salvage_action(raw)
        core_action = ({"op": "choose", "choice": "signal"} if action["op"] == "rescue"
                       else {"op": "wait"} if action["op"] in SPECIAL else action)
        before = digest(overlay)
        next_state = step(world, state, core_action)
        next_overlay = _transition(world, authored, overlay, state, next_state, action)
        event = {"sequence": len(events), "action": action, "before": before,
                 "after": digest(next_overlay), "world_after": digest(next_state),
                 "previous": previous}
        event["digest"] = digest(event)
        events.append(event)
        previous = event["digest"]
        state, overlay = next_state, next_overlay
        normalized.append(action)
        core_actions.append(core_action)
    if require_complete and not overlay["complete"]:
        raise HarborError("salvage rescue not completed")
    bundle = export_bundle(world, core_actions)
    if bundle["state"] != state:
        raise HarborError("salvage canonical replay divergence")
    report = {"schema": REPORT_SCHEMA, "source": world, "board": authored,
              "actions": normalized, "bundle": bundle, "events": events,
              "state": overlay, "source_digest": digest(world),
              "board_digest": digest(authored)}
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("salvage report exceeds byte budget")
    return report


def verify_salvage(report: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_KEYS, "salvage report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized salvage report")
    if report["report_digest"] != digest({k: v for k, v in report.items() if k != "report_digest"}):
        raise HarborError("salvage report digest mismatch")
    verify_bundle(report["bundle"])
    rebuilt = build_salvage(report["source"], report["board"], report["actions"],
                            require_complete=require_complete)
    if rebuilt != report:
        raise HarborError("salvage event or canonical replay mismatch")
    return {"complete": rebuilt["state"]["complete"], "failed": rebuilt["state"]["failed"],
            "secured": list(rebuilt["state"]["secured"]),
            "cargo": list(rebuilt["state"]["cargo"]),
            "hull": rebuilt["state"]["hull"], "reward": rebuilt["state"]["reward"],
            "tick": rebuilt["state"]["tick"],
            "position": list(rebuilt["bundle"]["state"]["pos"]),
            "report_digest": rebuilt["report_digest"]}


def resume_salvage(report: Any, actions: Any, *, expected_digest: str,
                   require_complete: bool = False) -> dict[str, Any]:
    verify_salvage(report)
    if type(expected_digest) is not str or expected_digest != report["report_digest"]:
        raise HarborError("stale salvage CAS lease")
    if report["state"]["complete"] or report["state"]["failed"]:
        raise HarborError("cannot resume terminal salvage mission")
    if not isinstance(actions, list):
        raise HarborError("invalid salvage continuation")
    return build_salvage(report["source"], report["board"], report["actions"] + actions,
                         require_complete=require_complete)
