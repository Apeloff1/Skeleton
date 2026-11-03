"""Pure turn engine: collision, survival, crafting, combat, rescue and consequences."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
from .schema import World, RECIPES

class RescueError(ValueError):
    pass

DIRECTIONS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
VERBS = frozenset({"move", "gather", "craft", "attack", "rescue", "rest", "signal", "evacuate"})
MAX_HISTORY = 8192

def _near(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) <= 1

def initial_state(world: World) -> dict:
    return {
        "schema": "ridge.rescue.state.v1", "turn": 0, "position": list(world.start),
        "health": 10, "stamina": 8, "inventory": {"wood": 0, "ore": 0, "herb": 0, "torch": 0, "bandage": 0, "signal": 0},
        "resources": {ident: count for ident, _, _, count in world.resources},
        "civilians": {ident: "waiting" for ident, _ in world.civilians},
        "raiders": {ident: {"at": list(at), "health": 3} for ident, at in world.raiders},
        "flags": {"beacon": False, "choice": None}, "status": "playing",
        "events": [],
    }

def _check(state: dict, world: World) -> None:
    if not isinstance(state, dict) or state.get("schema") != "ridge.rescue.state.v1":
        raise RescueError("invalid state")
    if state.get("status") != "playing":
        raise RescueError("game already ended")
    if state.get("turn", -1) >= world.max_turns:
        raise RescueError("turn budget exhausted")
    if state.get("health", 0) <= 0:
        raise RescueError("player defeated")

def _add_event(state: dict, event: str) -> None:
    if len(state["events"]) >= MAX_HISTORY:
        raise RescueError("event capacity exceeded")
    state["events"].append(event)

def _raider_positions(state: dict) -> set[tuple[int, int]]:
    return {tuple(v["at"]) for v in state["raiders"].values() if v["health"] > 0}

def _civilian_positions(state: dict, world: World) -> set[tuple[int, int]]:
    return {p for ident, p in world.civilians if state["civilians"][ident] == "waiting"}

def available_actions(world: World, state: dict) -> list[dict]:
    if state["status"] != "playing":
        return []
    here = tuple(state["position"])
    options: list[dict] = []
    for direction, (dx, dy) in DIRECTIONS.items():
        target = (here[0] + dx, here[1] + dy)
        if state["stamina"] > 0 and world.walkable(target) and world.tile(target) != "~" and target not in _raider_positions(state) and target not in _civilian_positions(state, world):
            options.append({"verb": "move", "direction": direction})
    for ident, kind, at, _ in world.resources:
        if state["resources"][ident] and _near(here, at):
            options.append({"verb": "gather", "target": ident})
    for item, recipe in RECIPES.items():
        if all(state["inventory"][kind] >= amount for kind, amount in recipe.items()):
            options.append({"verb": "craft", "item": item})
    for ident, raider in sorted(state["raiders"].items()):
        if state["stamina"] > 0 and raider["health"] and _near(here, tuple(raider["at"])):
            options.append({"verb": "attack", "target": ident})
    for ident, at in world.civilians:
        if state["civilians"][ident] == "waiting" and _near(here, at):
            options.append({"verb": "rescue", "target": ident})
    if state["inventory"]["signal"] and not state["flags"]["beacon"] and here == world.shelter:
        options.append({"verb": "signal"})
    if here == world.shelter and all(v != "waiting" for v in state["civilians"].values()):
        for choice in (("protect", "salvage") if state["flags"]["beacon"] else ("salvage",)):
            options.append({"verb": "evacuate", "choice": choice})
    options.append({"verb": "rest"})
    return options

def _enemies_advance(state: dict, world: World) -> None:
    # Deterministic guard movement: fixed ID order, no RNG, no diagonal or occupancy overlap.
    here = tuple(state["position"])
    occupied = {tuple(v["at"]) for v in state["raiders"].values() if v["health"] > 0}
    occupied.update(_civilian_positions(state, world))
    occupied.add(world.shelter)
    for ident in sorted(state["raiders"]):
        enemy = state["raiders"][ident]
        if enemy["health"] <= 0:
            continue
        pos = tuple(enemy["at"])
        if _near(pos, here):
            state["health"] = max(0, state["health"] - 1)
            _add_event(state, f"raider:{ident}:strike")
            continue
        candidates = []
        for dx, dy in DIRECTIONS.values():
            target = (pos[0] + dx, pos[1] + dy)
            if not world.walkable(target) or world.tile(target) == "~" or target in occupied or target == here:
                continue
            distance = abs(target[0] - here[0]) + abs(target[1] - here[1])
            candidates.append((distance, target[1], target[0], target))
        if candidates:
            best = min(candidates)[3]
            if abs(best[0] - here[0]) + abs(best[1] - here[1]) < abs(pos[0] - here[0]) + abs(pos[1] - here[1]):
                occupied.remove(pos)
                occupied.add(best)
                enemy["at"] = list(best)
                _add_event(state, f"raider:{ident}:move")

def apply(world: World, state: dict, action: dict[str, Any]) -> dict:
    _check(state, world)
    if not isinstance(action, dict) or set(action) - {"verb", "direction", "target", "item", "choice"}:
        raise RescueError("malformed action")
    if action not in available_actions(world, state):
        raise RescueError("unavailable action")
    result = deepcopy(state)
    here = tuple(result["position"])
    verb = action["verb"]
    if verb == "move":
        dx, dy = DIRECTIONS[action["direction"]]
        target = (here[0] + dx, here[1] + dy)
        result["position"] = list(target)
        result["stamina"] = max(0, result["stamina"] - 1)
        if world.tile(target) == "^":
            result["stamina"] = max(0, result["stamina"] - 1)
        _add_event(result, f"move:{action['direction']}")
    elif verb == "gather":
        ident = action["target"]
        kind = next(k for i, k, _, _ in world.resources if i == ident)
        result["resources"][ident] -= 1
        result["inventory"][kind] += 1
        _add_event(result, f"gather:{ident}:{kind}")
    elif verb == "craft":
        item = action["item"]
        for ingredient, amount in RECIPES[item].items():
            result["inventory"][ingredient] -= amount
        result["inventory"][item] += 1
        _add_event(result, f"craft:{item}")
    elif verb == "attack":
        ident = action["target"]
        enemy = result["raiders"][ident]
        damage = 2 if result["inventory"]["torch"] else 1
        enemy["health"] = max(0, enemy["health"] - damage)
        result["stamina"] = max(0, result["stamina"] - 1)
        _add_event(result, f"attack:{ident}:{damage}")
    elif verb == "rescue":
        ident = action["target"]
        result["civilians"][ident] = "rescued"
        _add_event(result, f"rescue:{ident}")
    elif verb == "rest":
        result["stamina"] = min(8, result["stamina"] + 3)
        if result["inventory"]["bandage"] and result["health"] < 10:
            result["inventory"]["bandage"] -= 1
            result["health"] = min(10, result["health"] + 3)
        _add_event(result, "rest")
    elif verb == "signal":
        result["inventory"]["signal"] -= 1
        result["flags"]["beacon"] = True
        _add_event(result, "beacon:lit")
    elif verb == "evacuate":
        choice = action["choice"]
        if choice == "protect" and not result["flags"]["beacon"]:
            raise RescueError("protect ending requires earned beacon")
        result["flags"]["choice"] = choice
        result["status"] = "won:protect" if choice == "protect" else "won:salvage"
        _add_event(result, f"ending:{choice}")
    result["turn"] += 1
    if result["status"] == "playing":
        if result["turn"] % 5 == 0:
            result["health"] = max(0, result["health"] - 1)
            _add_event(result, "storm:damage")
        _enemies_advance(result, world)
        if result["health"] == 0:
            result["status"] = "lost:health"
            _add_event(result, "ending:defeat")
        elif result["turn"] >= world.max_turns:
            result["status"] = "lost:time"
            _add_event(result, "ending:timeout")
    return result

def replay(world: World, actions: list[dict]) -> dict:
    if not isinstance(actions, list) or len(actions) > min(world.max_turns, MAX_HISTORY):
        raise RescueError("invalid action history length")
    state = initial_state(world)
    for action in actions:
        state = apply(world, state, action)
    return state
