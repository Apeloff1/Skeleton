"""Original Lantern Quay game: bounded movement, crafting, trading and replay custody.

The authored JSON is the sole source of world rules. No dynamic code, network or
unbounded procedural generation is involved. This is a playable terminal vertical,
not a claim that a packaged graphical game has been device-qualified.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SCHEMA = "skeleton.game.harbor.v1"
BUNDLE_SCHEMA = "skeleton.game.harbor.bundle.v1"
MAX_SOURCE_BYTES = 65536
MAX_BUNDLE_BYTES = 262144
MAX_TICKS = 1024
MAX_INVENTORY = 64
MAX_RESOURCES = 32
MAX_RECIPES = 32
DIRECTIONS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
SOURCE_KEYS = {"schema", "id", "map", "start", "resources", "npc", "recipes", "dock", "delivery", "max_ticks", "initial_coins"}


class HarborError(ValueError):
    """Fail-closed authoring, gameplay, or replay contract violation."""


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HarborError("duplicate JSON field")
        value[key] = item
    return value


def _bad_constant(value: str) -> None:
    raise HarborError("non-finite JSON constant")


def decode(raw: bytes, limit: int = MAX_BUNDLE_BYTES) -> Any:
    if len(raw) > limit:
        raise HarborError("input exceeds byte limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_bad_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise HarborError("invalid canonical JSON") from exc


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise HarborError("noncanonical data") from exc


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def _keys(value: Any, required: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise HarborError("invalid " + label + " fields")
    return value


def _integer(value: Any, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise HarborError("invalid " + label)
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 48:
        raise HarborError("invalid " + label)
    if not all(c.isascii() and (c.isalnum() or c in "_-") for c in value):
        raise HarborError("invalid " + label)
    return value


def _position(value: Any, tiles: list[str], label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 2:
        raise HarborError("invalid " + label)
    x = _integer(value[0], 0, len(tiles[0]) - 1, label + ".x")
    y = _integer(value[1], 0, len(tiles) - 1, label + ".y")
    if tiles[y][x] != ".":
        raise HarborError(label + " is blocked")
    return [x, y]


def _items(value: Any, label: str, *, allow_zero: bool = False) -> dict[str, int]:
    if not isinstance(value, dict) or not 1 <= len(value) <= 16:
        raise HarborError("invalid " + label)
    for item, quantity in value.items():
        _identifier(item, label + ".item")
        _integer(quantity, 0 if allow_zero else 1, MAX_INVENTORY, label + ".quantity")
    return value


def validate_source(value: Any) -> dict[str, Any]:
    source = _keys(value, SOURCE_KEYS, "source")
    if source["schema"] != SCHEMA:
        raise HarborError("unsupported world schema")
    _identifier(source["id"], "world id")
    tiles = source["map"]
    if not isinstance(tiles, list) or not 3 <= len(tiles) <= 32:
        raise HarborError("invalid map height")
    if not all(isinstance(row, str) and 3 <= len(row) <= 32 for row in tiles):
        raise HarborError("invalid map row")
    if len({len(row) for row in tiles}) != 1 or any(set(row) - set("#.") for row in tiles):
        raise HarborError("invalid map geometry")
    if any(c != "#" for c in tiles[0] + tiles[-1]):
        raise HarborError("map perimeter must be closed")
    if any(row[0] != "#" or row[-1] != "#" for row in tiles):
        raise HarborError("map perimeter must be closed")
    start = _position(source["start"], tiles, "start")
    dock = _position(source["dock"], tiles, "dock")
    if start == dock:
        raise HarborError("dock overlaps start")
    _integer(source["max_ticks"], 1, MAX_TICKS, "max_ticks")
    _integer(source["initial_coins"], 0, MAX_INVENTORY, "initial_coins")
    resources = source["resources"]
    if not isinstance(resources, list) or not 1 <= len(resources) <= MAX_RESOURCES:
        raise HarborError("invalid resources")
    seen_resource_positions: set[tuple[int, int]] = set()
    seen_resource_ids: set[str] = set()
    for resource in resources:
        _keys(resource, {"id", "at", "quantity"}, "resource")
        item = _identifier(resource["id"], "resource id")
        pos = _position(resource["at"], tiles, "resource")
        if item in seen_resource_ids or tuple(pos) in seen_resource_positions or pos in (start, dock):
            raise HarborError("duplicate or overlapping resource")
        seen_resource_ids.add(item)
        seen_resource_positions.add(tuple(pos))
        _integer(resource["quantity"], 1, MAX_INVENTORY, "resource quantity")
    npc = _keys(source["npc"], {"id", "route", "stock", "price"}, "npc")
    _identifier(npc["id"], "npc id")
    route = npc["route"]
    if not isinstance(route, list) or not 1 <= len(route) <= 16:
        raise HarborError("invalid NPC route")
    for point in route:
        pos = _position(point, tiles, "npc route")
        if pos in (start, dock):
            raise HarborError("NPC route overlaps player or dock")
    if len({tuple(point) for point in route}) != len(route):
        raise HarborError("duplicate NPC route point")
    _items(npc["stock"], "npc stock")
    _integer(npc["price"], 1, MAX_INVENTORY, "npc price")
    recipes = source["recipes"]
    if not isinstance(recipes, list) or not 1 <= len(recipes) <= MAX_RECIPES:
        raise HarborError("invalid recipes")
    recipe_ids: set[str] = set()
    for recipe in recipes:
        _keys(recipe, {"id", "inputs", "output"}, "recipe")
        name = _identifier(recipe["id"], "recipe id")
        if name in recipe_ids:
            raise HarborError("duplicate recipe")
        recipe_ids.add(name)
        _items(recipe["inputs"], "recipe inputs")
        _items(recipe["output"], "recipe output")
    _items(source["delivery"], "delivery")
    obtainable = seen_resource_ids | set(npc["stock"])
    for _ in range(MAX_RECIPES):
        for recipe in recipes:
            if set(recipe["inputs"]).issubset(obtainable):
                obtainable.update(recipe["output"])
    if not set(source["delivery"]).issubset(obtainable):
        raise HarborError("unobtainable delivery item")
    if len(canonical(source)) > MAX_SOURCE_BYTES:
        raise HarborError("source exceeds byte limit")
    return deepcopy(source)


def initial_state(source: dict[str, Any]) -> dict[str, Any]:
    world = validate_source(source)
    return {
        "tick": 0,
        "pos": list(world["start"]),
        "npc_pos": list(world["npc"]["route"][0]),
        "inventory": {},
        "stock": {item["id"]: item["quantity"] for item in world["resources"]},
        "npc_stock": dict(world["npc"]["stock"]),
        "coins": world["initial_coins"],
        "delivered": False,
        "ending": None,
        "reputation": 0,
    }


def _distance(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def normalize_action(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or "op" not in value:
        raise HarborError("action must be an object")
    op = value["op"]
    shapes = {
        "move": {"op", "direction"},
        "gather": {"op"},
        "craft": {"op", "recipe"},
        "trade": {"op", "item"},
        "deliver": {"op"},
        "choose": {"op", "choice"},
        "wait": {"op"},
    }
    if not isinstance(op, str) or op not in shapes or set(value) != shapes[op]:
        raise HarborError("unsupported action shape")
    for key in shapes[op] - {"op"}:
        _identifier(value[key], key)
    if op == "move" and value["direction"] not in DIRECTIONS:
        raise HarborError("unsupported direction")
    if op == "choose" and value["choice"] not in {"signal", "shelter"}:
        raise HarborError("unsupported consequence")
    return dict(value)


def step(source: dict[str, Any], state: dict[str, Any], action: Any) -> dict[str, Any]:
    action = normalize_action(action)
    if state["ending"] is not None:
        raise HarborError("campaign already complete")
    if state["tick"] >= source["max_ticks"]:
        raise HarborError("campaign tick budget exhausted")
    result = deepcopy(state)
    op = action["op"]
    if op == "move":
        dx, dy = DIRECTIONS[action["direction"]]
        x, y = result["pos"]
        target = [x + dx, y + dy]
        if not (0 <= target[1] < len(source["map"]) and 0 <= target[0] < len(source["map"][0])):
            raise HarborError("movement outside world")
        if source["map"][target[1]][target[0]] != "." or target == result["npc_pos"]:
            raise HarborError("movement collision")
        result["pos"] = target
    elif op == "gather":
        matching = [resource for resource in source["resources"] if resource["at"] == result["pos"]]
        if not matching:
            raise HarborError("no resource at player position")
        item = matching[0]["id"]
        if result["stock"][item] < 1:
            raise HarborError("resource exhausted")
        if sum(result["inventory"].values()) >= MAX_INVENTORY:
            raise HarborError("inventory capacity exceeded")
        result["stock"][item] -= 1
        result["inventory"][item] = result["inventory"].get(item, 0) + 1
    elif op == "craft":
        recipe = next((r for r in source["recipes"] if r["id"] == action["recipe"]), None)
        if recipe is None:
            raise HarborError("unknown recipe")
        if any(result["inventory"].get(item, 0) < qty for item, qty in recipe["inputs"].items()):
            raise HarborError("crafting materials missing")
        new_total = sum(result["inventory"].values()) - sum(recipe["inputs"].values()) + sum(recipe["output"].values())
        if new_total > MAX_INVENTORY:
            raise HarborError("inventory capacity exceeded")
        for item, qty in recipe["inputs"].items():
            result["inventory"][item] -= qty
        for item, qty in recipe["output"].items():
            result["inventory"][item] = result["inventory"].get(item, 0) + qty
        result["inventory"] = {k: v for k, v in result["inventory"].items() if v}
    elif op == "trade":
        item = action["item"]
        if _distance(result["pos"], result["npc_pos"]) != 1:
            raise HarborError("merchant out of reach")
        if item not in result["npc_stock"] or result["npc_stock"][item] < 1:
            raise HarborError("merchant out of stock")
        if result["coins"] < source["npc"]["price"]:
            raise HarborError("insufficient coins")
        if sum(result["inventory"].values()) >= MAX_INVENTORY:
            raise HarborError("inventory capacity exceeded")
        result["coins"] -= source["npc"]["price"]
        result["npc_stock"][item] -= 1
        result["inventory"][item] = result["inventory"].get(item, 0) + 1
    elif op == "deliver":
        if result["delivered"] or _distance(result["pos"], source["dock"]) != 1:
            raise HarborError("dock delivery unavailable")
        if any(result["inventory"].get(item, 0) < qty for item, qty in source["delivery"].items()):
            raise HarborError("required cargo missing")
        for item, qty in source["delivery"].items():
            result["inventory"][item] -= qty
        result["inventory"] = {k: v for k, v in result["inventory"].items() if v}
        result["delivered"] = True
        result["reputation"] += 1
    elif op == "choose":
        if not result["delivered"] or _distance(result["pos"], source["dock"]) != 1:
            raise HarborError("consequence not earned")
        result["ending"] = "beacon" if action["choice"] == "signal" else "safe_harbor"
        result["reputation"] += 2 if action["choice"] == "signal" else 1
    result["tick"] += 1
    next_npc = source["npc"]["route"][result["tick"] % len(source["npc"]["route"])]
    if next_npc != result["pos"]:
        result["npc_pos"] = list(next_npc)
    return result


def run(source: dict[str, Any], actions: list[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    world = validate_source(source)
    if not isinstance(actions, list) or len(actions) > world["max_ticks"]:
        raise HarborError("action count exceeds tick budget")
    state = initial_state(world)
    events: list[dict[str, Any]] = []
    previous = digest({"world": digest(world), "genesis": True})
    for action in actions:
        normalized = normalize_action(action)
        before = digest(state)
        updated = step(world, state, normalized)
        entry = {
            "sequence": len(events),
            "action": normalized,
            "before": before,
            "after": digest(updated),
            "previous": previous,
            "source": digest(world),
        }
        entry["digest"] = digest(entry)
        events.append(entry)
        previous = entry["digest"]
        state = updated
    return state, events


def export_bundle(source: dict[str, Any], actions: list[Any], *, require_win: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    state, events = run(world, actions)
    if require_win and state["ending"] is None:
        raise HarborError("victory not earned")
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "source": world,
        "source_digest": digest(world),
        "events": events,
        "state": state,
        "terminal_digest": digest(state),
    }
    bundle["bundle_digest"] = digest(bundle)
    if len(canonical(bundle)) > MAX_BUNDLE_BYTES:
        raise HarborError("bundle exceeds byte limit")
    return bundle


def verify_bundle(bundle: Any, *, require_win: bool = False) -> dict[str, Any]:
    _keys(bundle, {"schema", "source", "source_digest", "events", "state", "terminal_digest", "bundle_digest"}, "bundle")
    if bundle["schema"] != BUNDLE_SCHEMA or len(canonical(bundle)) > MAX_BUNDLE_BYTES:
        raise HarborError("unsupported or oversized bundle")
    world = validate_source(bundle["source"])
    if bundle["source_digest"] != digest(world):
        raise HarborError("source digest mismatch")
    if bundle["bundle_digest"] != digest({k: v for k, v in bundle.items() if k != "bundle_digest"}):
        raise HarborError("bundle digest mismatch")
    if not isinstance(bundle["events"], list) or len(bundle["events"]) > world["max_ticks"]:
        raise HarborError("event budget exceeded")
    actions = []
    for event in bundle["events"]:
        _keys(event, {"sequence", "action", "before", "after", "previous", "source", "digest"}, "event")
        actions.append(normalize_action(event["action"]))
    try:
        state, expected_events = run(world, actions)
    except HarborError as exc:
        # An invalid replay action cannot be accepted merely by resealing
        # the bundle checksum; it is an untrusted event-chain mismatch.
        raise HarborError("replay event chain mismatch") from exc
    if expected_events != bundle["events"]:
        raise HarborError("replay event chain mismatch")
    if state != bundle["state"] or digest(state) != bundle["terminal_digest"]:
        raise HarborError("replay terminal mismatch")
    if require_win and state["ending"] is None:
        raise HarborError("victory not earned")
    return deepcopy(state)


def load_source(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        raise HarborError("cannot read world source") from exc
    return validate_source(decode(raw, MAX_SOURCE_BYTES))


def demo_actions() -> list[dict[str, str]]:
    return [
        {"op": "move", "direction": "east"}, {"op": "gather"}, {"op": "gather"},
        {"op": "move", "direction": "east"}, {"op": "gather"},
        {"op": "move", "direction": "west"}, {"op": "move", "direction": "west"},
        {"op": "move", "direction": "south"}, {"op": "move", "direction": "south"},
        {"op": "gather"}, {"op": "craft", "recipe": "lantern"},
        {"op": "craft", "recipe": "ration"},
        {"op": "move", "direction": "east"}, {"op": "move", "direction": "east"},
        {"op": "move", "direction": "east"}, {"op": "move", "direction": "east"},
        {"op": "deliver"}, {"op": "choose", "choice": "signal"},
    ]
