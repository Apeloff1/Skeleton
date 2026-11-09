"""Playable tile movement and collision over the canonical scene-travel engine.

Authored tiles restrict where a player can collect or traverse a scene exit.
Canonical scene transitions still own inventory, locked exits and endings.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance as advance_scene, _id, _limit, _object,
    new_session, normalize_world, original_demo,
)

SCHEMA = "skeleton.scene_tile_walk.v1"
BUNDLE = "skeleton.scene_tile_walk_bundle.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_STEPS = 256
DIRECTIONS = {"north": (0, -1), "south": (0, 1),
              "east": (1, 0), "west": (-1, 0)}


def _bounded(payload: Any, maximum: int = MAX_BYTES) -> None:
    try:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise SceneTravelError("invalid tile walk JSON") from exc
    if len(data) > maximum:
        raise SceneTravelError("tile walk JSON size budget exceeded")


def _point(raw: Any, width: int, height: int) -> list[int]:
    if type(raw) is not list or len(raw) != 2:
        raise SceneTravelError("invalid tile coordinate")
    return [_limit(raw[0], "tile x", 0, width - 1),
            _limit(raw[1], "tile y", 0, height - 1)]


def _reachable(width: int, height: int, spawn: list[int],
               walls: set[tuple[int, int]]) -> set[tuple[int, int]]:
    seen = {tuple(spawn)}
    pending = deque([tuple(spawn)])
    while pending:
        x, y = pending.popleft()
        for dx, dy in DIRECTIONS.values():
            p = (x + dx, y + dy)
            if (0 <= p[0] < width and 0 <= p[1] < height
                    and p not in walls and p not in seen):
                seen.add(p)
                pending.append(p)
    return seen


def normalize_tiles(raw: Any) -> dict[str, Any]:
    _bounded(raw, 128 * 1024)
    obj = _object(raw, {"schema_version", "world", "maps", "step_limit"},
                  "tile source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported tile schema")
    world = normalize_world(obj["world"])
    budget = _limit(obj["step_limit"], "tile step budget", 1, MAX_STEPS)
    raw_maps = obj["maps"]
    if type(raw_maps) is not list or len(raw_maps) != len(world["scenes"]):
        raise SceneTravelError("tile map count must match authored scenes")
    scenes = {s["id"]: s for s in world["scenes"]}
    seen: set[str] = set()
    maps = []
    for entry in raw_maps:
        area = _object(entry, {"scene_id", "width", "height", "spawn",
                               "walls", "pickups", "exits"}, "tile map")
        ident = _id(area["scene_id"], "tile scene")
        if ident not in scenes or ident in seen:
            raise SceneTravelError("unknown or duplicate tile scene")
        seen.add(ident)
        width = _limit(area["width"], "tile width", 2, 16)
        height = _limit(area["height"], "tile height", 2, 16)
        spawn = _point(area["spawn"], width, height)
        if type(area["walls"]) is not list or len(area["walls"]) > width * height:
            raise SceneTravelError("invalid tile walls")
        walls = [_point(point, width, height) for point in area["walls"]]
        blocked = {tuple(p) for p in walls}
        if len(blocked) != len(walls) or tuple(spawn) in blocked:
            raise SceneTravelError("duplicate wall or blocked spawn")
        occupied: set[tuple[int, int]] = set()
        interactions = []
        cleaned: dict[str, list[dict[str, Any]]] = {}
        for kind in ("pickups", "exits"):
            raw_items = area[kind]
            authored = {item["id"] for item in scenes[ident][kind]}
            if type(raw_items) is not list or len(raw_items) != len(authored):
                raise SceneTravelError("tile interaction count mismatch")
            items = []
            for raw_item in raw_items:
                item = _object(raw_item, {"id", "at"}, "tile interaction")
                item_id = _id(item["id"], "tile interaction id")
                point = _point(item["at"], width, height)
                if (item_id not in authored or tuple(point) in blocked
                        or tuple(point) in occupied):
                    raise SceneTravelError("unbound or blocked tile interaction")
                occupied.add(tuple(point))
                items.append({"id": item_id, "at": point})
                interactions.append(tuple(point))
            if len({item["id"] for item in items}) != len(items):
                raise SceneTravelError("duplicate tile interaction")
            cleaned[kind] = sorted(items, key=lambda item: item["id"])
        reachable = _reachable(width, height, spawn, blocked)
        if any(point not in reachable for point in interactions):
            raise SceneTravelError("unreachable tile interaction")
        maps.append({"scene_id": ident, "width": width, "height": height,
                     "spawn": spawn, "walls": sorted(walls),
                     "pickups": cleaned["pickups"], "exits": cleaned["exits"]})
    return {"schema_version": SCHEMA, "world": world,
            "maps": sorted(maps, key=lambda item: item["scene_id"]),
            "step_limit": budget}


def _area(source: dict[str, Any], scene_id: str) -> dict[str, Any]:
    return next(area for area in source["maps"] if area["scene_id"] == scene_id)


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "tile.action", event["action"]["kind"], event["receipt"])
        for i, event in enumerate(journal)
    )).digest


def new_tiles(source: Any) -> dict[str, Any]:
    spec = normalize_tiles(source)
    scene = new_session(spec["world"])
    state = {"tick": 0, "scene": scene,
             "position": list(_area(spec, spec["world"]["start_scene"])["spawn"]),
             "phase": "active"}
    return {"schema_version": SCHEMA, "source": spec,
            "source_digest": dig(spec), "state": state,
            "state_digest": dig(state), "journal": [],
            "event_bus_digest": EventBus().digest, "save": _save(spec, state)}


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid tile action")
    kind = raw.get("kind")
    if kind == "move":
        _object(raw, {"kind", "direction"}, "tile movement")
        if type(raw["direction"]) is not str or raw["direction"] not in DIRECTIONS:
            raise SceneTravelError("invalid tile direction")
        return {"kind": "move", "direction": raw["direction"]}
    if kind in ("collect", "travel"):
        field = "pickup_id" if kind == "collect" else "exit_id"
        _object(raw, {"kind", field}, "tile interaction")
        return {"kind": kind, field: _id(raw[field], field)}
    raise SceneTravelError("unsupported tile action")


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    before, source = session["state"], session["source"]
    if before["phase"] != "active":
        raise SceneTravelError("tile walk already terminal")
    if before["tick"] >= source["step_limit"]:
        raise SceneTravelError("tile walk step budget exhausted")
    action = _action(raw)
    scene = before["scene"]
    area = _area(source, scene["state"]["scene_id"])
    position = list(before["position"])
    if action["kind"] == "move":
        dx, dy = DIRECTIONS[action["direction"]]
        nxt = [position[0] + dx, position[1] + dy]
        if (not 0 <= nxt[0] < area["width"]
                or not 0 <= nxt[1] < area["height"] or nxt in area["walls"]):
            raise SceneTravelError("tile collision or map boundary")
        position = nxt
    else:
        kind = "pickups" if action["kind"] == "collect" else "exits"
        key = "pickup_id" if kind == "pickups" else "exit_id"
        target = next((p for p in area[kind] if p["id"] == action[key]), None)
        if target is None or target["at"] != position:
            raise SceneTravelError("tile interaction not at player position")
        scene = advance_scene(scene, action)
        if kind == "exits":
            position = list(_area(source, scene["state"]["scene_id"])["spawn"])
    state = {"tick": before["tick"] + 1, "scene": scene,
             "position": position, "phase": scene["state"]["phase"]}
    event = {"sequence": before["tick"], "action": action,
             "before": session["state_digest"], "after": dig(state)}
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {"schema_version": SCHEMA, "source": source,
              "source_digest": session["source_digest"], "state": state,
              "state_digest": dig(state), "journal": journal,
              "event_bus_digest": _bus(journal),
              "save": _save(source, state, session["save"])}
    _bounded(result)
    return result


def verify_tiles(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {"schema_version", "source", "source_digest",
                            "state", "state_digest", "journal",
                            "event_bus_digest", "save"}, "tile save")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported tile save")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid tile journal")
    rebuilt = new_tiles(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid tile event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("tile replay receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("tile replay or save mismatch")
    return rebuilt


def resume_tiles(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_tiles(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid tile action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_tiles(source: Any, actions: Any) -> dict[str, Any]:
    return resume_tiles(new_tiles(source), actions)


def export_tiles(payload: Any) -> dict[str, Any]:
    session = verify_tiles(payload)
    bundle = {"schema_version": BUNDLE, "source_digest": session["source_digest"],
              "state_digest": session["state_digest"], "session": session}
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_tiles(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {"schema_version", "source_digest",
                            "state_digest", "session", "checksum"}, "tile bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported tile bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("tile bundle checksum mismatch")
    session = verify_tiles(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise SceneTravelError("tile bundle source/state mismatch")
    return session


def original_tiles() -> tuple[dict[str, Any], list[dict[str, str]]]:
    world, _ = original_demo()
    source = {"schema_version": SCHEMA, "world": world, "step_limit": 16,
              "maps": [
                  {"scene_id": "quay", "width": 4, "height": 3,
                   "spawn": [0, 1], "walls": [[1, 0], [1, 2]],
                   "pickups": [{"id": "find_key", "at": [1, 1]}],
                   "exits": [{"id": "north", "at": [3, 1]},
                             {"id": "down", "at": [0, 2]}]},
                  {"scene_id": "gate", "width": 3, "height": 3,
                   "spawn": [0, 1], "walls": [], "pickups": [],
                   "exits": [{"id": "inside", "at": [2, 1]}]},
                  {"scene_id": "sanctuary", "width": 2, "height": 2,
                   "spawn": [0, 0], "walls": [], "pickups": [], "exits": []},
                  {"scene_id": "sinkhole", "width": 2, "height": 2,
                   "spawn": [0, 0], "walls": [], "pickups": [], "exits": []},
              ]}
    actions = [{"kind": "move", "direction": "east"},
               {"kind": "collect", "pickup_id": "find_key"},
               {"kind": "move", "direction": "east"},
               {"kind": "move", "direction": "east"},
               {"kind": "travel", "exit_id": "north"},
               {"kind": "move", "direction": "east"},
               {"kind": "move", "direction": "east"},
               {"kind": "travel", "exit_id": "inside"}]
    return source, actions


def _json(raw: str) -> Any:
    if type(raw) is not str:
        raise SceneTravelError("invalid tile JSON")
    try:
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise SceneTravelError("tile JSON size budget exceeded")
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate JSON key")
                obj[key] = value
            return obj
        def nonfinite(_: str) -> Any:
            raise ValueError("nonfinite JSON number")
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid tile JSON") from exc


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-tiles")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("simulate", "resume"):
        p = sub.add_parser(command)
        p.add_argument("--source-json" if command == "simulate"
                       else "--session-json", required=True)
        p.add_argument("--actions-json", required=True)
    for command in ("verify", "export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_tiles()
            result = simulate_tiles(source, actions)
        elif args.command == "simulate":
            result = simulate_tiles(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_tiles(_json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_tiles(_json(args.session_json))
        elif args.command == "export":
            result = export_tiles(_json(args.session_json))
        else:
            result = import_tiles(_json(args.bundle_json))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, TypeError, ValueError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
