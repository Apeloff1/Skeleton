"""Source-bound push-block puzzles on the canonical scene tile runtime.

The tile runtime owns movement, pickups, scene transitions and endings. This
overlay only owns movable crates and pressure-plate exit conditions. Every
checkpoint is rebuilt from authored source and an exact ordered action journal.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.scene_tile_walk import (
    DIRECTIONS, MAX_BYTES, MAX_STEPS, _advance as tile_advance,
    _area, _bounded, _json, _point, new_tiles, normalize_tiles, original_tiles,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_tile_push.v1"
BUNDLE = "skeleton.scene_tile_push_bundle.v1"
MAX_OBJECTS = 32
MAX_EDITS = 16


def _location(entry: dict[str, Any], areas: dict[str, dict[str, Any]],
              label: str) -> tuple[str, list[int]]:
    scene_id = _id(entry["scene_id"], label + " scene")
    if scene_id not in areas:
        raise SceneTravelError(label + " references unknown scene")
    area = areas[scene_id]
    point = _point(entry["at"], area["width"], area["height"])
    if point in area["walls"]:
        raise SceneTravelError(label + " intersects wall")
    return scene_id, point


def normalize_push(raw: Any) -> dict[str, Any]:
    _bounded(raw, 256 * 1024)
    obj = _object(raw, {
        "schema_version", "tile_source", "crates", "plates", "locks",
        "turn_limit",
    }, "push source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported push source schema")
    tiles = normalize_tiles(obj["tile_source"])
    areas = {area["scene_id"]: area for area in tiles["maps"]}
    turn_limit = _limit(obj["turn_limit"], "push turn limit", 1, MAX_STEPS)
    if turn_limit > tiles["step_limit"]:
        raise SceneTravelError("push turn limit exceeds canonical tile budget")
    for field in ("crates", "plates", "locks"):
        if type(obj[field]) is not list or len(obj[field]) > MAX_OBJECTS:
            raise SceneTravelError("invalid push " + field + " count")
    if not obj["crates"] or not obj["plates"] or not obj["locks"]:
        raise SceneTravelError("push puzzle needs crates, plates and locks")
    crates, occupied, crate_ids = [], set(), set()
    for entry in obj["crates"]:
        item = _object(entry, {"id", "scene_id", "at"}, "push crate")
        ident = _id(item["id"], "crate id")
        scene, point = _location(item, areas, "crate")
        key = (scene, *point)
        area = areas[scene]
        interactions = [x["at"] for x in area["pickups"] + area["exits"]]
        if (ident in crate_ids or key in occupied or point == area["spawn"]
                or point in interactions):
            raise SceneTravelError("crate overlaps spawn, interaction or crate")
        crate_ids.add(ident)
        occupied.add(key)
        crates.append({"id": ident, "scene_id": scene, "at": point})
    plates, plate_ids, plate_locations = [], set(), set()
    for entry in obj["plates"]:
        item = _object(entry, {"id", "scene_id", "at"}, "push plate")
        ident = _id(item["id"], "plate id")
        scene, point = _location(item, areas, "plate")
        key = (scene, *point)
        if ident in plate_ids or key in plate_locations:
            raise SceneTravelError("duplicate plate id or location")
        plate_ids.add(ident)
        plate_locations.add(key)
        plates.append({"id": ident, "scene_id": scene, "at": point})
    locks, exit_keys = [], set()
    authored_exits = {
        (area["scene_id"], edge["id"])
        for area in tiles["maps"] for edge in area["exits"]
    }
    for entry in obj["locks"]:
        item = _object(entry, {"scene_id", "exit_id", "requires_plates"},
                       "push lock")
        scene = _id(item["scene_id"], "lock scene")
        exit_id = _id(item["exit_id"], "lock exit")
        key = (scene, exit_id)
        required = item["requires_plates"]
        if (key not in authored_exits or key in exit_keys
                or type(required) is not list
                or not 1 <= len(required) <= MAX_OBJECTS):
            raise SceneTravelError("invalid or duplicate push lock")
        ids = [_id(p, "required plate") for p in required]
        if len(set(ids)) != len(ids) or not set(ids) <= plate_ids:
            raise SceneTravelError("push lock requires unknown/duplicate plate")
        exit_keys.add(key)
        locks.append({"scene_id": scene, "exit_id": exit_id,
                      "requires_plates": sorted(ids)})
    return {
        "schema_version": SCHEMA, "tile_source": tiles,
        "crates": sorted(crates, key=lambda x: x["id"]),
        "plates": sorted(plates, key=lambda x: x["id"]),
        "locks": sorted(locks, key=lambda x: (x["scene_id"], x["exit_id"])),
        "turn_limit": turn_limit,
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["tile_source"]["world"]["world_id"],
        schema_version=1, tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "tile.push", entry["action"]["kind"], entry["receipt"])
        for i, entry in enumerate(journal)
    )).digest


def new_push(source: Any) -> dict[str, Any]:
    spec = normalize_push(source)
    tile = new_tiles(spec["tile_source"])
    state = {
        "tick": 0, "tile": tile,
        "crates": {crate["id"]: {
            "scene_id": crate["scene_id"], "at": list(crate["at"]),
        } for crate in spec["crates"]},
        "phase": tile["state"]["phase"],
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(spec, state),
    }


def _plate_state(source: dict[str, Any],
                 crates: dict[str, dict[str, Any]]) -> dict[str, bool]:
    positions = {(v["scene_id"], *v["at"]) for v in crates.values()}
    return {
        plate["id"]: (plate["scene_id"], *plate["at"]) in positions
        for plate in source["plates"]
    }


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid push action")
    kind = raw.get("kind")
    if kind == "move":
        obj = _object(raw, {"kind", "direction"}, "push movement")
        direction = obj["direction"]
        if type(direction) is not str or direction not in DIRECTIONS:
            raise SceneTravelError("invalid push direction")
        return {"kind": "move", "direction": direction}
    if kind in ("collect", "travel"):
        field = "pickup_id" if kind == "collect" else "exit_id"
        obj = _object(raw, {"kind", field}, "push interaction")
        return {"kind": kind, field: _id(obj[field], field)}
    raise SceneTravelError("unsupported push action")


def _step(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, before = session["source"], session["state"]
    if before["phase"] != "active":
        raise SceneTravelError("push puzzle already terminal")
    if before["tick"] >= source["turn_limit"]:
        raise SceneTravelError("push turn budget exhausted")
    action = _action(raw)
    tile = before["tile"]
    scene_id = tile["state"]["scene"]["state"]["scene_id"]
    area = _area(source["tile_source"], scene_id)
    crates = copy.deepcopy(before["crates"])
    if action["kind"] == "move":
        dx, dy = DIRECTIONS[action["direction"]]
        x, y = tile["state"]["position"]
        target = [x + dx, y + dy]
        crate_id = next((ident for ident, value in crates.items()
                         if value["scene_id"] == scene_id
                         and value["at"] == target), None)
        if crate_id is not None:
            destination = [target[0] + dx, target[1] + dy]
            occupied = any(
                value["scene_id"] == scene_id and value["at"] == destination
                for ident, value in crates.items() if ident != crate_id
            )
            interaction = any(
                item["at"] == destination
                for item in area["pickups"] + area["exits"]
            )
            if (not 0 <= destination[0] < area["width"]
                    or not 0 <= destination[1] < area["height"]
                    or destination in area["walls"] or occupied or interaction):
                raise SceneTravelError("crate collision or blocked destination")
            crates[crate_id]["at"] = destination
    elif action["kind"] == "travel":
        plates = _plate_state(source, crates)
        for lock in source["locks"]:
            if lock["scene_id"] == scene_id and lock["exit_id"] == action["exit_id"]:
                if not all(plates[ident] for ident in lock["requires_plates"]):
                    raise SceneTravelError("exit locked by inactive pressure plates")
    tile = tile_advance(tile, action)
    state = {
        "tick": before["tick"] + 1, "tile": tile,
        "crates": crates, "phase": tile["state"]["phase"],
    }
    event = {
        "sequence": before["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _bus(journal),
        "save": _save(source, state, session["save"]),
    }
    _bounded(result, MAX_BYTES)
    return result


def verify_push(payload: Any) -> dict[str, Any]:
    _bounded(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "push save")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported push save schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_STEPS:
        raise SceneTravelError("invalid push journal")
    rebuilt = new_push(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid push journal entry")
        rebuilt = _step(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("push replay receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("push source/state/save replay mismatch")
    return rebuilt


def resume_push(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_push(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid push action batch")
    for action in actions:
        session = _step(session, action)
    return verify_push(session)


def simulate_push(source: Any, actions: Any) -> dict[str, Any]:
    return resume_push(new_push(source), actions)


def export_push(payload: Any) -> dict[str, Any]:
    session = verify_push(payload)
    bundle = {
        "schema_version": BUNDLE, "kind": "offline_tile_push",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle, MAX_BYTES)
    return bundle


def import_push(payload: Any) -> dict[str, Any]:
    _bounded(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "kind", "source_digest",
        "state_digest", "session", "checksum",
    }, "push bundle")
    if obj["schema_version"] != BUNDLE or obj["kind"] != "offline_tile_push":
        raise SceneTravelError("unsupported push bundle")
    if type(obj["checksum"]) is not str or obj["checksum"] != dig({
        key: value for key, value in obj.items() if key != "checksum"
    }):
        raise SceneTravelError("push bundle checksum mismatch")
    session = verify_push(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise SceneTravelError("push bundle source/state mismatch")
    return session


def legal_push_actions(payload: Any) -> list[dict[str, str]]:
    session = verify_push(payload)
    if (session["state"]["phase"] != "active"
            or session["state"]["tick"] >= session["source"]["turn_limit"]):
        return []
    tile = session["state"]["tile"]
    scene_id = tile["state"]["scene"]["state"]["scene_id"]
    area = _area(session["source"]["tile_source"], scene_id)
    candidates = [{"kind": "move", "direction": direction}
                  for direction in sorted(DIRECTIONS)]
    candidates.extend({"kind": "collect", "pickup_id": item["id"]}
                      for item in area["pickups"])
    candidates.extend({"kind": "travel", "exit_id": item["id"]}
                      for item in area["exits"])
    legal = []
    for candidate in candidates:
        try:
            _step(session, candidate)
        except SceneTravelError:
            continue
        legal.append(candidate)
    return legal


def edit_push(source: Any, expected_digest: str, edits: Any,
              preview_actions: Any = None) -> dict[str, Any]:
    spec = normalize_push(source)
    if type(expected_digest) is not str or dig(spec) != expected_digest:
        raise SceneTravelError("push author source digest conflict")
    if type(edits) is not list or len(edits) > MAX_EDITS:
        raise SceneTravelError("invalid push author edit batch")
    changed = copy.deepcopy(spec)
    for raw in edits:
        item = _object(raw, {"kind", "id", "scene_id", "at"}, "push edit")
        kind = item["kind"]
        if kind not in ("relocate_crate", "relocate_plate"):
            raise SceneTravelError("unsupported push author operation")
        field = "crates" if kind == "relocate_crate" else "plates"
        ident = _id(item["id"], "push author id")
        target = next((entry for entry in changed[field]
                       if entry["id"] == ident), None)
        if target is None:
            raise SceneTravelError("push author references missing object")
        target["scene_id"] = item["scene_id"]
        target["at"] = item["at"]
    changed = normalize_push(changed)
    preview = (simulate_push(changed, preview_actions)
               if preview_actions is not None else None)
    return {
        "schema_version": "skeleton.scene_tile_push_author.v1",
        "previous_digest": expected_digest,
        "source_digest": dig(changed), "source": changed,
        "preview": preview,
    }


def original_push() -> tuple[dict[str, Any], list[dict[str, str]]]:
    tiles, _ = original_tiles()
    tiles["step_limit"] = 32
    quay = next(area for area in tiles["maps"] if area["scene_id"] == "quay")
    quay.update({
        "width": 5, "height": 4, "spawn": [0, 1],
        "walls": [[1, 0], [1, 3]],
        "pickups": [{"id": "find_key", "at": [0, 2]}],
        "exits": [{"id": "north", "at": [4, 1]},
                  {"id": "down", "at": [0, 3]}],
    })
    source = {
        "schema_version": SCHEMA, "tile_source": tiles, "turn_limit": 32,
        "crates": [{"id": "iron_block", "scene_id": "quay", "at": [1, 1]}],
        "plates": [{"id": "gate_plate", "scene_id": "quay", "at": [2, 1]}],
        "locks": [{"scene_id": "quay", "exit_id": "north",
                   "requires_plates": ["gate_plate"]}],
    }
    actions = [
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "west"},
        {"kind": "move", "direction": "south"},
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "north"},
        {"kind": "move", "direction": "east"},
        {"kind": "travel", "exit_id": "north"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "east"},
        {"kind": "travel", "exit_id": "inside"},
    ]
    return source, actions


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-push")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sim = sub.add_parser("simulate")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for name in ("verify", "export", "legal"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    author = sub.add_parser("author")
    author.add_argument("--source-json", required=True)
    author.add_argument("--expected-digest", required=True)
    author.add_argument("--edits-json", required=True)
    author.add_argument("--preview-actions-json")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--max-states", type=int, default=512)
    solve.add_argument("--max-depth", type=int, default=24)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_push()
            result = simulate_push(source, actions)
        elif args.command == "simulate":
            result = simulate_push(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_push(_json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_push(_json(args.session_json))
        elif args.command == "export":
            result = export_push(_json(args.session_json))
        elif args.command == "legal":
            result = legal_push_actions(_json(args.session_json))
        elif args.command == "import":
            result = import_push(_json(args.bundle_json))
        elif args.command == "author":
            result = edit_push(
                _json(args.source_json), args.expected_digest,
                _json(args.edits_json),
                _json(args.preview_actions_json)
                if args.preview_actions_json is not None else None,
            )
        else:
            from skeleton.game.gameplay.scene_tile_push_solver import solve_push
            result = solve_push(
                _json(args.source_json), max_states=args.max_states,
                max_depth=args.max_depth,
            )
        _bounded(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
