"""Source-bound stealth patrol: authored guards, earned objectives and replay."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, normalize_action,
    step, validate_source, verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.patrol-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.patrol-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 4
MAX_GUARDS = 6
MAX_OBJECTIVES = 12
BOARD_KEYS = {"schema", "source_id", "guards", "objectives", "exit",
              "max_turns", "alert_limit", "smoke_item"}
GUARD_KEYS = {"id", "route", "sight"}
OBJECTIVE_KEYS = {"id", "at", "reward"}
REPORT_KEYS = {"schema", "source", "board", "actions", "bundle", "events",
               "state", "source_digest", "board_digest", "report_digest"}
SPECIAL = {"collect", "hide", "smoke", "extract"}


def _tile(value: Any, world: dict[str, Any], label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 2:
        raise HarborError("invalid " + label)
    x = _integer(value[0], 0, len(world["map"][0]) - 1, label + ".x")
    y = _integer(value[1], 0, len(world["map"]) - 1, label + ".y")
    if world["map"][y][x] != ".":
        raise HarborError(label + " is blocked")
    return [x, y]


def _distance(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def validate_patrol_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_KEYS, "patrol board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("patrol source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("patrol board exceeds byte budget")
    _integer(board["max_turns"], 1, world["max_ticks"], "patrol turn budget")
    _integer(board["alert_limit"], 1, 12, "patrol alert limit")
    item = _identifier(board["smoke_item"], "patrol smoke item")
    if item not in {name for recipe in world["recipes"] for name in recipe["output"]}:
        raise HarborError("patrol smoke item must be craftable")
    exit_at = _tile(board["exit"], world, "patrol exit")
    if _distance(exit_at, world["dock"]) != 1:
        raise HarborError("patrol exit must be adjacent to delivery dock")
    guards = board["guards"]
    if not isinstance(guards, list) or not 1 <= len(guards) <= MAX_GUARDS:
        raise HarborError("invalid patrol guard count")
    seen: set[str] = set()
    for guard in guards:
        _keys(guard, GUARD_KEYS, "patrol guard")
        name = _identifier(guard["id"], "patrol guard id")
        if name in seen:
            raise HarborError("duplicate patrol guard")
        seen.add(name)
        _integer(guard["sight"], 0, 3, "patrol guard sight")
        route = guard["route"]
        if not isinstance(route, list) or not 1 <= len(route) <= 16:
            raise HarborError("invalid patrol guard route")
        points = [_tile(point, world, "patrol guard route") for point in route]
        if len({tuple(point) for point in points}) != len(points):
            raise HarborError("duplicate patrol guard route point")
        if world["start"] in points or world["dock"] in points:
            raise HarborError("patrol guard route overlaps spawn or dock")
    objectives = board["objectives"]
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= MAX_OBJECTIVES:
        raise HarborError("invalid patrol objective count")
    names: set[str] = set()
    locations: set[tuple[int, int]] = set()
    for objective in objectives:
        _keys(objective, OBJECTIVE_KEYS, "patrol objective")
        name = _identifier(objective["id"], "patrol objective id")
        pos = _tile(objective["at"], world, "patrol objective")
        _integer(objective["reward"], 1, 100, "patrol objective reward")
        if name in names or tuple(pos) in locations:
            raise HarborError("duplicate patrol objective")
        if pos == world["dock"] or pos == world["start"]:
            raise HarborError("patrol objective overlaps spawn or dock")
        names.add(name)
        locations.add(tuple(pos))
    return deepcopy(board)


def normalize_patrol_action(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict) and type(raw.get("op")) is str and raw["op"] in SPECIAL:
        op = raw["op"]
        if op == "collect":
            _keys(raw, {"op", "objective"}, "patrol collect action")
            return {"op": op, "objective": _identifier(raw["objective"], "patrol objective")}
        _keys(raw, {"op"}, "patrol special action")
        return {"op": op}
    action = normalize_action(raw)
    if action["op"] == "choose":
        raise HarborError("direct choice bypasses patrol extraction")
    return action


def initial_patrol_state(board: dict[str, Any]) -> dict[str, Any]:
    return {"tick": 0, "alert": 0, "collected": [], "score": 0,
            "smoke_used": False, "complete": False, "failed": False,
            "guards": [list(g["route"][0]) for g in board["guards"]]}


def _advance(world: dict[str, Any], board: dict[str, Any],
             overlay: dict[str, Any], after: dict[str, Any],
             action: dict[str, str]) -> dict[str, Any]:
    if overlay["complete"] or overlay["failed"]:
        raise HarborError("patrol already terminal")
    result = deepcopy(overlay)
    result["tick"] += 1
    if result["tick"] > board["max_turns"]:
        raise HarborError("patrol turn budget exhausted")
    guards = [list(guard["route"][result["tick"] % len(guard["route"])])
              for guard in board["guards"]]
    result["guards"] = guards
    op = action["op"]
    if op == "collect":
        objective = next((obj for obj in board["objectives"]
                          if obj["id"] == action["objective"]), None)
        if objective is None or objective["id"] in result["collected"]:
            raise HarborError("unknown or already collected patrol objective")
        if after["pos"] != objective["at"] or after["pos"] in guards:
            raise HarborError("patrol objective requires unoccupied authored tile")
        result["collected"].append(objective["id"])
        result["score"] += objective["reward"]
    if op == "smoke":
        if result["smoke_used"] or after["inventory"].get(board["smoke_item"], 0) < 1:
            raise HarborError("patrol smoke requires earned unused crafted item")
        result["smoke_used"] = True
    spotted = any(_distance(after["pos"], pos) <= guard["sight"]
                  for guard, pos in zip(board["guards"], guards))
    if spotted and op != "smoke":
        result["alert"] += 1
    elif op == "hide" and not spotted:
        result["alert"] = max(0, result["alert"] - 1)
    if result["alert"] >= board["alert_limit"]:
        result["failed"] = True
    if op == "extract":
        if (result["failed"] or len(result["collected"]) != len(board["objectives"])
                or after["pos"] != board["exit"] or not after["delivered"]
                or after["ending"] != "beacon"):
            raise HarborError("patrol extraction not earned")
        result["complete"] = True
    return result


def build_patrol(source: Any, board: Any, actions: Any, *,
                 require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_patrol_board(board, world)
    if not isinstance(actions, list) or len(actions) > authored["max_turns"]:
        raise HarborError("patrol action count exceeds budget")
    core = initial_state(world)
    overlay = initial_patrol_state(authored)
    core_actions: list[dict[str, str]] = []
    normalized: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    previous = digest({"source": digest(world), "board": digest(authored), "genesis": True})
    for raw in actions:
        action = normalize_patrol_action(raw)
        core_action = ({"op": "choose", "choice": "signal"} if action["op"] == "extract"
                       else {"op": "wait"} if action["op"] in SPECIAL else action)
        before = digest(overlay)
        next_core = step(world, core, core_action)
        next_overlay = _advance(world, authored, overlay, next_core, action)
        event = {"sequence": len(events), "action": action, "before": before,
                 "after": digest(next_overlay), "world_after": digest(next_core),
                 "previous": previous}
        event["digest"] = digest(event)
        events.append(event)
        previous = event["digest"]
        core, overlay = next_core, next_overlay
        normalized.append(action)
        core_actions.append(core_action)
    if require_complete and not overlay["complete"]:
        raise HarborError("patrol extraction not completed")
    bundle = export_bundle(world, core_actions)
    if bundle["state"] != core:
        raise HarborError("patrol canonical replay divergence")
    report = {"schema": REPORT_SCHEMA, "source": world, "board": authored,
              "actions": normalized, "bundle": bundle, "events": events,
              "state": overlay, "source_digest": digest(world),
              "board_digest": digest(authored)}
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("patrol report exceeds byte budget")
    return report


def verify_patrol(report: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_KEYS, "patrol report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized patrol report")
    if report["report_digest"] != digest({k: v for k, v in report.items()
                                           if k != "report_digest"}):
        raise HarborError("patrol report digest mismatch")
    verify_bundle(report["bundle"])
    rebuilt = build_patrol(report["source"], report["board"], report["actions"],
                           require_complete=require_complete)
    if rebuilt != report:
        raise HarborError("patrol replay mismatch")
    return {"complete": rebuilt["state"]["complete"],
            "failed": rebuilt["state"]["failed"],
            "score": rebuilt["state"]["score"],
            "alert": rebuilt["state"]["alert"],
            "collected": list(rebuilt["state"]["collected"]),
            "position": list(rebuilt["bundle"]["state"]["pos"]),
            "report_digest": rebuilt["report_digest"]}


def resume_patrol(report: Any, actions: Any, *, expected_digest: str,
                  require_complete: bool = False) -> dict[str, Any]:
    verify_patrol(report)
    if type(expected_digest) is not str or expected_digest != report["report_digest"]:
        raise HarborError("stale patrol CAS lease")
    if report["state"]["complete"] or report["state"]["failed"]:
        raise HarborError("cannot resume terminal patrol")
    if not isinstance(actions, list):
        raise HarborError("invalid patrol continuation")
    return build_patrol(report["source"], report["board"],
                        report["actions"] + actions, require_complete=require_complete)
