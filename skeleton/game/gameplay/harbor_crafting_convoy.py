"""Source-bound playable convoy escort, deterministic tactical encounters and custody.

All player movement, gathering and crafting is delegated to the canonical
Lantern Quay engine. Escort, guard and strike consume canonical wait ticks;
the convoy overlay never grants unearned canonical inventory or currency.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    DIRECTIONS, HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, normalize_action, step,
    validate_source, verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.convoy-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.convoy-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 4
MAX_ROUTE = 32
MAX_ENCOUNTERS = 12
BOARD_FIELDS = {"schema", "source_id", "route", "encounters", "hull", "weapon_item", "max_turns"}
ENCOUNTER_FIELDS = {"id", "at_index", "strength", "reward"}
REPORT_FIELDS = {
    "schema", "source", "board", "actions", "bundle", "events", "state",
    "source_digest", "board_digest", "report_digest",
}
SPECIAL = {"escort", "strike", "guard"}


def _distance(left: list[int], right: list[int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def validate_convoy_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_FIELDS, "convoy board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("convoy board source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("convoy board exceeds byte budget")
    _integer(board["hull"], 1, 20, "convoy hull")
    _integer(board["max_turns"], 1, world["max_ticks"], "convoy turn budget")
    weapon = _identifier(board["weapon_item"], "convoy weapon")
    craftable = {
        item for recipe in world["recipes"] for item in recipe["output"]
    }
    if weapon not in craftable:
        raise HarborError("convoy weapon must be craftable in the source")
    route = board["route"]
    if not isinstance(route, list) or not 2 <= len(route) <= MAX_ROUTE:
        raise HarborError("invalid convoy route length")
    for index, point in enumerate(route):
        if (not isinstance(point, list) or len(point) != 2
                or any(type(v) is not int for v in point)):
            raise HarborError("invalid convoy waypoint")
        x, y = point
        if (not 0 <= y < len(world["map"])
                or not 0 <= x < len(world["map"][0])
                or world["map"][y][x] != "."):
            raise HarborError("convoy waypoint is not traversable")
        if index and _distance(route[index - 1], point) != 1:
            raise HarborError("convoy route is not contiguous")
    if route[-1] != world["dock"]:
        raise HarborError("convoy must finish at the authored dock")
    if route[0] == world["start"]:
        raise HarborError("convoy cannot spawn on player")
    if any(point in world["npc"]["route"] for point in route):
        raise HarborError("convoy route collides with merchant patrol")
    encounters = board["encounters"]
    if not isinstance(encounters, list) or len(encounters) > MAX_ENCOUNTERS:
        raise HarborError("invalid convoy encounters")
    seen: set[str] = set()
    indexes: set[int] = set()
    for encounter in encounters:
        _keys(encounter, ENCOUNTER_FIELDS, "convoy encounter")
        name = _identifier(encounter["id"], "convoy encounter id")
        index = _integer(encounter["at_index"], 1, len(route) - 1, "encounter waypoint")
        _integer(encounter["strength"], 1, 12, "encounter strength")
        _integer(encounter["reward"], 0, 100, "encounter reward")
        if name in seen or index in indexes:
            raise HarborError("duplicate convoy encounter or waypoint")
        seen.add(name)
        indexes.add(index)
    return deepcopy(board)


def normalize_convoy_action(value: Any) -> dict[str, str]:
    if isinstance(value, dict) and type(value.get("op")) is str and value["op"] in SPECIAL:
        _keys(value, {"op"}, "convoy action")
        return {"op": value["op"]}
    return normalize_action(value)


def _initial(board: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": 0, "hull": board["hull"], "threat": None,
        "spent": 0, "bounty": 0, "tick": 0,
        "complete": False, "failed": False,
    }


def _transition(world: dict[str, Any], board: dict[str, Any],
                convoy: dict[str, Any], before: dict[str, Any],
                after: dict[str, Any], action: dict[str, str]) -> dict[str, Any]:
    if convoy["complete"] or convoy["failed"]:
        raise HarborError("convoy run already terminal")
    updated = deepcopy(convoy)
    op = action["op"]
    current = board["route"][updated["index"]]
    if after["pos"] == current:
        raise HarborError("player collided with convoy")
    if op == "escort":
        if updated["threat"] is not None:
            raise HarborError("convoy cannot advance during combat")
        if updated["index"] + 1 >= len(board["route"]):
            raise HarborError("convoy already at destination")
        target = board["route"][updated["index"] + 1]
        if (_distance(after["pos"], current) > 2
                or _distance(after["pos"], target) > 2
                or after["pos"] == target):
            raise HarborError("escort requires a nearby unobstructed waypoint")
        updated["index"] += 1
    elif op == "strike":
        if updated["threat"] is None:
            raise HarborError("no convoy threat to strike")
        if _distance(after["pos"], current) > 2:
            raise HarborError("convoy threat out of reach")
        available = after["inventory"].get(board["weapon_item"], 0)
        if available <= updated["spent"]:
            raise HarborError("no earned unspent convoy weapon charge")
        updated["spent"] += 1
        updated["threat"]["remaining"] -= 1
        if updated["threat"]["remaining"] == 0:
            updated["bounty"] += updated["threat"]["reward"]
            updated["threat"] = None
    elif op == "guard":
        if updated["threat"] is None or _distance(after["pos"], current) > 2:
            raise HarborError("guard requires a nearby active convoy threat")
    if convoy["threat"] is not None and updated["threat"] is not None and op != "guard":
        updated["hull"] -= 1
        if updated["hull"] == 0:
            updated["failed"] = True
    if op == "escort":
        for encounter in board["encounters"]:
            if encounter["at_index"] == updated["index"]:
                updated["threat"] = {
                    "id": encounter["id"],
                    "remaining": encounter["strength"],
                    "reward": encounter["reward"],
                }
                break
    updated["tick"] += 1
    if updated["tick"] > board["max_turns"]:
        raise HarborError("convoy authored turn budget exhausted")
    if updated["index"] == len(board["route"]) - 1 and updated["threat"] is None and not updated["failed"]:
        updated["complete"] = True
    return updated


def build_convoy(source: Any, board: Any, actions: Any, *,
                 require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_convoy_board(board, world)
    if not isinstance(actions, list) or len(actions) > authored["max_turns"]:
        raise HarborError("convoy action count exceeds turn budget")
    state = initial_state(world)
    convoy = _initial(authored)
    events: list[dict[str, Any]] = []
    core_actions: list[dict[str, str]] = []
    normalized_actions: list[dict[str, str]] = []
    previous = digest({"source": digest(world), "board": digest(authored), "genesis": True})
    for action in actions:
        normalized = normalize_convoy_action(action)
        canonical_action = {"op": "wait"} if normalized["op"] in SPECIAL else normalized
        before = digest(convoy)
        updated_world = step(world, state, canonical_action)
        updated = _transition(world, authored, convoy, state, updated_world, normalized)
        event = {
            "sequence": len(events), "action": normalized, "before": before,
            "after": digest(updated), "world_after": digest(updated_world),
            "previous": previous,
        }
        event["digest"] = digest(event)
        events.append(event)
        previous = event["digest"]
        state, convoy = updated_world, updated
        core_actions.append(canonical_action)
        normalized_actions.append(normalized)
    if require_complete and not convoy["complete"]:
        raise HarborError("convoy delivery not earned")
    bundle = export_bundle(world, core_actions)
    if bundle["state"] != state:
        raise HarborError("convoy and canonical gameplay diverged")
    report = {
        "schema": REPORT_SCHEMA, "source": world, "board": authored,
        "actions": normalized_actions, "bundle": bundle,
        "events": events, "state": convoy,
        "source_digest": digest(world), "board_digest": digest(authored),
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("convoy report exceeds byte budget")
    return report


def verify_convoy(report: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "convoy report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized convoy report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("convoy report digest mismatch")
    verify_bundle(report["bundle"])
    rebuilt = build_convoy(
        report["source"], report["board"], report["actions"],
        require_complete=require_complete,
    )
    if rebuilt != report:
        raise HarborError("convoy replay mismatch")
    return {
        "complete": rebuilt["state"]["complete"],
        "failed": rebuilt["state"]["failed"],
        "hull": rebuilt["state"]["hull"],
        "bounty": rebuilt["state"]["bounty"],
        "waypoint": rebuilt["state"]["index"],
        "tick": rebuilt["state"]["tick"],
        "report_digest": rebuilt["report_digest"],
    }


def resume_convoy(report: Any, actions: Any, *, expected_digest: str,
                  require_complete: bool = False) -> dict[str, Any]:
    verify_convoy(report)
    if type(expected_digest) is not str or expected_digest != report["report_digest"]:
        raise HarborError("stale convoy checkpoint")
    if report["state"]["complete"] or report["state"]["failed"]:
        raise HarborError("terminal convoy checkpoint cannot advance")
    if not isinstance(actions, list) or not actions:
        raise HarborError("convoy continuation requires actions")
    resumed = build_convoy(
        report["source"], report["board"], report["actions"] + actions,
        require_complete=require_complete,
    )
    if resumed["events"][:len(report["events"])] != report["events"]:
        raise HarborError("convoy continuation rewrote history")
    return resumed


def convoy_status(report: Any) -> dict[str, Any]:
    verified = verify_convoy(report)
    threat = report["state"]["threat"]
    return {
        **verified,
        "position": deepcopy(report["board"]["route"][report["state"]["index"]]),
        "threat": deepcopy(threat),
        "next_waypoint": (
            deepcopy(report["board"]["route"][report["state"]["index"] + 1])
            if report["state"]["index"] + 1 < len(report["board"]["route"]) else None
        ),
        "weapon_charges_spent": report["state"]["spent"],
    }
