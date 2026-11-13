"""Source-bound quest board for the playable Lantern Quay campaign.

Mission progress is a derived view of canonical gameplay transitions. It never
mutates the player save, trusts a supplied achievement, or awards a victory.
The exported report carries the original world and the complete verified replay.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, initial_state, normalize_action, step, validate_source,
    verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.mission-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.mission-report.v1"
MAX_MISSIONS = 12
MAX_OBJECTIVES = 12
MAX_TOTAL_OBJECTIVES = 64
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 2
OBJECTIVE_FIELDS = {
    "gather": {"kind", "item", "count"},
    "craft": {"kind", "recipe", "count"},
    "trade": {"kind", "item", "count"},
    "visit": {"kind", "at"},
    "deliver": {"kind"},
    "choose": {"kind", "choice"},
    "inventory": {"kind", "item", "quantity"},
    "reputation": {"kind", "minimum"},
}


def validate_board(board: Any, source: Any) -> dict[str, Any]:
    """Check complete authored contract, dependencies, and world binding."""
    world = validate_source(source)
    _keys(board, {"schema", "source_id", "missions"}, "mission board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("mission board source mismatch")
    missions = board["missions"]
    if not isinstance(missions, list) or not 1 <= len(missions) <= MAX_MISSIONS:
        raise HarborError("invalid mission count")
    if len(canonical(board)) > 32768:
        raise HarborError("mission board exceeds byte limit")
    known: set[str] = set()
    total = 0
    resource_ids = {r["id"] for r in world["resources"]}
    recipe_ids = {r["id"] for r in world["recipes"]}
    items = resource_ids | set(world["npc"]["stock"]) | set(world["delivery"])
    for recipe in world["recipes"]:
        items.update(recipe["inputs"])
        items.update(recipe["output"])
    for mission in missions:
        _keys(mission, {"id", "requires", "objectives", "points", "deadline"}, "mission")
        name = _identifier(mission["id"], "mission id")
        if name in known:
            raise HarborError("duplicate mission id")
        requires = mission["requires"]
        if not isinstance(requires, list) or len(requires) > MAX_MISSIONS:
            raise HarborError("invalid mission prerequisites")
        if any(type(req) is not str for req in requires):
            raise HarborError("invalid mission prerequisite type")
        if len(set(requires)) != len(requires) or any(req not in known for req in requires):
            raise HarborError("mission prerequisites must precede their mission")
        _integer(mission["points"], 1, 100, "mission points")
        _integer(mission["deadline"], 1, world["max_ticks"], "mission deadline")
        objectives = mission["objectives"]
        if not isinstance(objectives, list) or not 1 <= len(objectives) <= MAX_OBJECTIVES:
            raise HarborError("invalid mission objectives")
        total += len(objectives)
        if total > MAX_TOTAL_OBJECTIVES:
            raise HarborError("mission objective budget exceeded")
        for objective in objectives:
            if not isinstance(objective, dict):
                raise HarborError("invalid objective")
            kind = objective.get("kind")
            if type(kind) is not str or kind not in OBJECTIVE_FIELDS:
                raise HarborError("unknown mission objective")
            _keys(objective, OBJECTIVE_FIELDS[kind], "mission objective")
            if kind in ("gather", "trade", "inventory"):
                item = _identifier(objective["item"], "objective item")
                if item not in items or (kind == "gather" and item not in resource_ids):
                    raise HarborError("objective item absent from world")
            if kind == "trade" and objective["item"] not in world["npc"]["stock"]:
                raise HarborError("objective merchant item absent")
            if kind == "craft" and _identifier(objective["recipe"], "objective recipe") not in recipe_ids:
                raise HarborError("objective recipe absent")
            if kind in ("gather", "craft", "trade"):
                _integer(objective["count"], 1, 64, "objective count")
            if kind == "inventory":
                _integer(objective["quantity"], 1, 64, "objective quantity")
            if kind == "reputation":
                _integer(objective["minimum"], 1, 3, "objective reputation")
            if kind == "visit":
                at = objective["at"]
                if not isinstance(at, list) or len(at) != 2:
                    raise HarborError("invalid visit coordinate")
                x = _integer(at[0], 0, len(world["map"][0]) - 1, "visit x")
                y = _integer(at[1], 0, len(world["map"]) - 1, "visit y")
                if world["map"][y][x] != ".":
                    raise HarborError("visit objective is blocked")
            if kind == "choose" and (
                type(objective["choice"]) is not str
                or objective["choice"] not in ("signal", "shelter")
            ):
                raise HarborError("invalid objective consequence")
        known.add(name)
    return deepcopy(board)


def _matches(
    objective: dict[str, Any], action: dict[str, str],
    before: dict[str, Any], after: dict[str, Any],
    source: dict[str, Any],
) -> bool:
    kind = objective["kind"]
    op = action["op"]
    if kind == "gather":
        return op == "gather" and any(
            r["id"] == objective["item"] and r["at"] == before["pos"]
            for r in source["resources"]
        )
    if kind == "craft":
        return op == "craft" and action["recipe"] == objective["recipe"]
    if kind == "trade":
        return op == "trade" and action["item"] == objective["item"]
    if kind == "visit":
        return op == "move" and after["pos"] == objective["at"]
    if kind == "deliver":
        return op == "deliver" and not before["delivered"] and after["delivered"]
    if kind == "choose":
        return op == "choose" and action["choice"] == objective["choice"] and after["ending"] is not None
    if kind == "inventory":
        return (
            before["inventory"].get(objective["item"], 0) < objective["quantity"]
            and after["inventory"].get(objective["item"], 0) >= objective["quantity"]
        )
    if kind == "reputation":
        return before["reputation"] < objective["minimum"] <= after["reputation"]
    raise HarborError("unreachable mission objective")


def _target(objective: dict[str, Any]) -> int:
    return objective["count"] if objective["kind"] in ("gather", "craft", "trade") else 1


def mission_report(bundle: Any, board: Any, *, require_all: bool = False) -> dict[str, Any]:
    """Replay canonical actions and derive ordered mission progress from events."""
    verify_bundle(bundle)
    source = validate_source(bundle["source"])
    authored = validate_board(board, source)
    state = initial_state(source)
    completed: list[str] = []
    progress = {
        mission["id"]: [0] * len(mission["objectives"])
        for mission in authored["missions"]
    }
    journal: list[dict[str, Any]] = []
    points = 0
    previous = digest({"board": digest(authored), "bundle": bundle["bundle_digest"]})
    for event in bundle["events"]:
        action = normalize_action(event["action"])
        before = state
        state = step(source, before, action)
        completed_before = frozenset(completed)
        for mission in authored["missions"]:
            name = mission["id"]
            if name in completed or state["tick"] > mission["deadline"]:
                continue
            if not set(mission["requires"]).issubset(completed_before):
                continue
            counts = progress[name]
            for index, objective in enumerate(mission["objectives"]):
                if counts[index] < _target(objective) and _matches(objective, action, before, state, source):
                    counts[index] += 1
            if all(counts[index] == _target(obj) for index, obj in enumerate(mission["objectives"])):
                completed.append(name)
                points += mission["points"]
        entry = {
            "tick": state["tick"],
            "event_digest": event["digest"],
            "state_digest": digest(state),
            "completed": list(completed),
            "progress": deepcopy(progress),
            "points": points,
            "previous": previous,
        }
        entry["digest"] = digest(entry)
        journal.append(entry)
        previous = entry["digest"]
    if state != bundle["state"]:
        raise HarborError("mission replay diverged from canonical state")
    if require_all and len(completed) != len(authored["missions"]):
        raise HarborError("mission board not fully earned")
    report = {
        "schema": REPORT_SCHEMA,
        "board": authored,
        "board_digest": digest(authored),
        "bundle": deepcopy(bundle),
        "source_digest": bundle["source_digest"],
        "journal": journal,
        "completed": completed,
        "points": points,
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("mission report exceeds byte limit")
    return report


def verify_mission_report(report: Any, *, require_all: bool = False) -> dict[str, Any]:
    """Reject forged progress even when an attacker recomputes outer hashes."""
    _keys(report, {
        "schema", "board", "board_digest", "bundle", "source_digest",
        "journal", "completed", "points", "report_digest",
    }, "mission report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized mission report")
    if report["report_digest"] != digest({k: v for k, v in report.items() if k != "report_digest"}):
        raise HarborError("mission report digest mismatch")
    if report["board_digest"] != digest(report["board"]):
        raise HarborError("mission board digest mismatch")
    if not isinstance(report["bundle"], dict) or report["source_digest"] != report["bundle"].get("source_digest"):
        raise HarborError("mission source digest mismatch")
    replayed = mission_report(report["bundle"], report["board"], require_all=require_all)
    if replayed != report:
        raise HarborError("mission progress replay mismatch")
    return {"completed": deepcopy(replayed["completed"]), "points": replayed["points"]}


def solve_missions(source: Any, board: Any, *, choice: str = "signal") -> dict[str, Any]:
    """Plan authored quests in dependency order using real gameplay transitions.

    The mission solver deliberately does not invent events or use mission progress
    as an authority. Every action is executed by the same movement, economy,
    collision, crafting and ending rules as a human player's session.
    """
    from .harbor_crafting import export_bundle
    from .harbor_crafting_planner import _CampaignPlanner, _distance
    world = validate_source(source)
    authored = validate_board(board, world)
    if type(choice) is not str or choice not in ("signal", "shelter"):
        raise HarborError("invalid mission ending choice")
    planner = _CampaignPlanner(world)
    for mission in authored["missions"]:
        for objective in mission["objectives"]:
            kind = objective["kind"]
            count = _target(objective)
            for _ in range(count):
                if kind == "gather":
                    resource = next(r for r in world["resources"] if r["id"] == objective["item"])
                    planner.navigate(lambda state, at=resource["at"]: state["pos"] == at)
                    planner.emit({"op": "gather"})
                elif kind == "craft":
                    recipe = next(r for r in world["recipes"] if r["id"] == objective["recipe"])
                    for item, quantity in sorted(recipe["inputs"].items()):
                        planner.ensure(item, quantity)
                    planner.emit({"op": "craft", "recipe": recipe["id"]})
                elif kind == "trade":
                    planner.navigate(
                        lambda state: _distance(state["pos"], state["npc_pos"]) == 1
                    )
                    planner.emit({"op": "trade", "item": objective["item"]})
                elif kind == "visit":
                    already_at_target = planner.state["pos"] == objective["at"]
                    if not already_at_target:
                        planner.navigate(
                            lambda state, at=objective["at"]: state["pos"] == at
                        )
                    else:
                        # An objective needs an actual move INTO its destination;
                        # standing on it from a prior mission does not count.
                        from .harbor_crafting_planner import MOVES
                        returned = False
                        for action in MOVES:
                            if action["op"] != "move":
                                continue
                            try:
                                after = step(world, planner.state, action)
                            except HarborError:
                                continue
                            if after["pos"] == objective["at"]:
                                continue
                            planner.emit(action)
                            planner.navigate(
                                lambda state, at=objective["at"]: state["pos"] == at
                            )
                            returned = True
                            break
                        if not returned:
                            raise HarborError("visit requires a reachable movement transition")
                elif kind == "inventory":
                    planner.ensure(objective["item"], objective["quantity"])
                elif kind == "deliver":
                    for item, quantity in sorted(world["delivery"].items()):
                        planner.ensure(item, quantity)
                    planner.navigate(
                        lambda state: _distance(state["pos"], world["dock"]) == 1
                    )
                    planner.emit({"op": "deliver"})
                elif kind == "choose":
                    if objective["choice"] != choice:
                        raise HarborError("mission choice conflicts with requested ending")
                    planner.navigate(
                        lambda state: _distance(state["pos"], world["dock"]) == 1
                    )
                    planner.emit({"op": "choose", "choice": choice})
                elif kind == "reputation":
                    if planner.state["reputation"] < objective["minimum"]:
                        raise HarborError("reputation requires prior earned delivery or choice")
                else:
                    raise HarborError("mission solver does not support objective")
        if planner.state["tick"] > mission["deadline"]:
            raise HarborError("mission solver missed authored deadline")
    if planner.state["ending"] is None:
        for item, quantity in sorted(world["delivery"].items()):
            planner.ensure(item, quantity)
        if not planner.state["delivered"]:
            planner.navigate(lambda state: _distance(state["pos"], world["dock"]) == 1)
            planner.emit({"op": "deliver"})
        planner.navigate(lambda state: _distance(state["pos"], world["dock"]) == 1)
        planner.emit({"op": "choose", "choice": choice})
    bundle = export_bundle(world, planner.actions, require_win=True)
    report = mission_report(bundle, authored, require_all=True)
    if verify_mission_report(report, require_all=True)["points"] != report["points"]:
        raise HarborError("mission solver replay mismatch")
    return report
