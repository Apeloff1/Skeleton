"""Source-bound tile survival: collision, hazards, food, shelter and replay.

The canonical tile engine owns navigation, pickups, locked exits and endings.
This overlay owns only survival consequences; it cannot forge canonical items.
All source is inert JSON, all effects are deterministic and replay-verifiable.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.scene_tile_walk import (
    MAX_BYTES, MAX_STEPS, _advance as advance_tile, _bounded,
    _point, _reachable, new_tiles, normalize_tiles, original_tiles,
    verify_tiles,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _limit, _object,
)

SCHEMA = "skeleton.scene_tile_survival.v1"
BUNDLE = "skeleton.scene_tile_survival_bundle.v1"
MAX_HAZARDS = 64
MAX_CAMPS = 32


def _location(raw: Any, areas: dict[str, dict[str, Any]],
              label: str) -> tuple[str, list[int]]:
    entry = _object(raw, {"scene_id", "at"}, label)
    scene_id = _id(entry["scene_id"], label + " scene")
    if scene_id not in areas:
        raise SceneTravelError("survival location references unknown scene")
    area = areas[scene_id]
    point = _point(entry["at"], area["width"], area["height"])
    if point in area["walls"]:
        raise SceneTravelError("survival location intersects wall")
    reachable = _reachable(
        area["width"], area["height"], area["spawn"],
        {tuple(w) for w in area["walls"]},
    )
    if tuple(point) not in reachable:
        raise SceneTravelError("survival location is unreachable")
    return scene_id, point


def normalize_survival(raw: Any) -> dict[str, Any]:
    _bounded(raw, 256 * 1024)
    obj = _object(raw, {
        "schema_version", "tile_source", "max_health", "max_food",
        "initial_food", "turn_limit", "hazards", "camps", "food_pickups",
    }, "survival source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported survival source schema")
    tiles = normalize_tiles(obj["tile_source"])
    health = _limit(obj["max_health"], "max health", 1, 100)
    food = _limit(obj["max_food"], "max food", 1, 32)
    initial = _limit(obj["initial_food"], "initial food", 0, food)
    limit = _limit(obj["turn_limit"], "survival turn limit", 1, MAX_STEPS)
    if type(obj["hazards"]) is not list or len(obj["hazards"]) > MAX_HAZARDS:
        raise SceneTravelError("invalid survival hazards")
    if type(obj["camps"]) is not list or len(obj["camps"]) > MAX_CAMPS:
        raise SceneTravelError("invalid survival camps")
    areas = {area["scene_id"]: area for area in tiles["maps"]}
    hazards = []
    for raw_hazard in obj["hazards"]:
        hazard = _object(raw_hazard, {"scene_id", "at", "damage"}, "hazard")
        scene_id, point = _location(
            {"scene_id": hazard["scene_id"], "at": hazard["at"]},
            areas, "hazard",
        )
        damage = _limit(hazard["damage"], "hazard damage", 1, 100)
        hazards.append({"scene_id": scene_id, "at": point, "damage": damage})
    keys = [(h["scene_id"], *h["at"]) for h in hazards]
    if len(keys) != len(set(keys)):
        raise SceneTravelError("duplicate survival hazard tile")
    camps = []
    for raw_camp in obj["camps"]:
        scene_id, point = _location(raw_camp, areas, "camp")
        camps.append({"scene_id": scene_id, "at": point})
    camp_keys = [(c["scene_id"], *c["at"]) for c in camps]
    if len(camp_keys) != len(set(camp_keys)):
        raise SceneTravelError("duplicate survival camp tile")
    if set(keys) & set(camp_keys):
        raise SceneTravelError("camp cannot overlap hazard")
    pickups = obj["food_pickups"]
    if type(pickups) is not list or len(pickups) > 256:
        raise SceneTravelError("invalid food pickup references")
    authored = {
        area["scene_id"] + ":" + item["id"]
        for area in tiles["maps"] for item in area["pickups"]
    }
    validated = [_id(item, "food pickup") for item in pickups]
    if len(set(validated)) != len(validated) or not set(validated) <= authored:
        raise SceneTravelError("food must reference unique authored pickups")
    return {
        "schema_version": SCHEMA, "tile_source": tiles,
        "max_health": health, "max_food": food, "initial_food": initial,
        "turn_limit": limit,
        "hazards": sorted(hazards, key=lambda h: (h["scene_id"], h["at"])),
        "camps": sorted(camps, key=lambda c: (c["scene_id"], c["at"])),
        "food_pickups": sorted(validated),
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          previous: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["tile_source"]["world"]["world_id"],
        schema_version=1, tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(spec),
        parent_save_digest=dig(previous) if previous is not None else None,
    ).__dict__)


def _bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "survival.action", entry["action"]["kind"],
                      entry["receipt"])
        for i, entry in enumerate(journal)
    )).digest


def new_survival(source: Any) -> dict[str, Any]:
    spec = normalize_survival(source)
    tile = new_tiles(spec["tile_source"])
    state = {
        "tick": 0, "tile": tile, "health": spec["max_health"],
        "food": spec["initial_food"], "used_camps": [], "phase": "active",
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid survival action")
    if raw.get("kind") == "rest":
        _object(raw, {"kind"}, "rest action")
        return {"kind": "rest"}
    if raw.get("kind") == "tile":
        _object(raw, {"kind", "action"}, "survival tile action")
        tile = raw["action"]
        if type(tile) is not dict or tile.get("kind") not in (
            "move", "collect", "travel",
        ):
            raise SceneTravelError("invalid nested tile action")
        return {"kind": "tile", "action": tile}
    raise SceneTravelError("unsupported survival action")


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old, spec = session["state"], session["source"]
    if old["phase"] != "active":
        raise SceneTravelError("survival already terminal")
    if old["tick"] >= spec["turn_limit"]:
        raise SceneTravelError("survival turn budget exhausted")
    action = _action(raw)
    state = {
        "tick": old["tick"] + 1, "tile": old["tile"],
        "health": old["health"], "food": old["food"],
        "used_camps": list(old["used_camps"]), "phase": "active",
    }
    if action["kind"] == "rest":
        tile_state = old["tile"]["state"]
        scene_id = tile_state["scene"]["state"]["scene_id"]
        position = tile_state["position"]
        camp_id = scene_id + ":" + str(position[0]) + ":" + str(position[1])
        if (not any(c["scene_id"] == scene_id and c["at"] == position
                    for c in spec["camps"]) or camp_id in old["used_camps"]):
            raise SceneTravelError("rest requires an unused camp at position")
        if old["food"] == 0 or old["health"] == spec["max_health"]:
            raise SceneTravelError("rest requires earned food and missing health")
        state["food"] -= 1
        state["health"] += 1
        state["used_camps"].append(camp_id)
        state["used_camps"].sort()
    else:
        before = old["tile"]["state"]
        tile = advance_tile(old["tile"], action["action"])
        after = tile["state"]
        state["tile"] = tile
        if action["action"]["kind"] == "collect":
            previous = set(before["scene"]["state"]["collected"])
            collected = set(after["scene"]["state"]["collected"]) - previous
            if collected & set(spec["food_pickups"]):
                state["food"] = min(spec["max_food"], old["food"] + 1)
        if action["action"]["kind"] == "move":
            scene_id = after["scene"]["state"]["scene_id"]
            damage = sum(
                h["damage"] for h in spec["hazards"]
                if h["scene_id"] == scene_id and h["at"] == after["position"]
            )
            state["health"] = max(0, old["health"] - damage)
    if state["health"] == 0:
        state["phase"] = "lost"
    elif state["tile"]["state"]["phase"] != "active":
        state["phase"] = state["tile"]["state"]["phase"]
    elif state["tick"] >= spec["turn_limit"]:
        state["phase"] = "draw"
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _bus(journal),
        "save": _save(spec, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_survival(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state", "state_digest",
        "journal", "event_bus_digest", "save",
    }, "survival session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported survival save")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid survival journal")
    rebuilt = new_survival(obj["source"])
    for entry in obj["journal"]:
        if type(entry) is not dict or "action" not in entry:
            raise SceneTravelError("invalid survival replay event")
        rebuilt = _advance(rebuilt, entry["action"])
        if rebuilt["journal"][-1] != entry:
            raise SceneTravelError("survival replay receipt mismatch")
    if rebuilt != obj or verify_tiles(rebuilt["state"]["tile"]) != rebuilt["state"]["tile"]:
        raise SceneTravelError("survival save or source mismatch")
    return rebuilt


def resume_survival(payload: Any, actions: Any) -> dict[str, Any]:
    current = verify_survival(payload)
    if type(actions) is not list or len(actions) + len(current["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid survival action batch")
    for action in actions:
        current = _advance(current, action)
    return current


def simulate_survival(source: Any, actions: Any) -> dict[str, Any]:
    return resume_survival(new_survival(source), actions)


def export_survival(payload: Any) -> dict[str, Any]:
    saved = verify_survival(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"], "session": saved,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_survival(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "survival bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported survival bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("survival bundle checksum mismatch")
    saved = verify_survival(obj["session"])
    if (saved["source_digest"] != obj["source_digest"]
            or saved["state_digest"] != obj["state_digest"]):
        raise SceneTravelError("survival bundle lineage mismatch")
    return saved


def original_survival() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tiles, actions = original_tiles()
    source = {
        "schema_version": SCHEMA, "tile_source": tiles,
        "max_health": 3, "max_food": 2, "initial_food": 0,
        "turn_limit": 16,
        "hazards": [{"scene_id": "quay", "at": [2, 1], "damage": 1}],
        "camps": [{"scene_id": "gate", "at": [0, 1]}],
        "food_pickups": ["quay:find_key"],
    }
    sequence = [{"kind": "tile", "action": a} for a in actions]
    sequence.insert(5, {"kind": "rest"})
    return source, sequence


def _json(raw: str) -> Any:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise SceneTravelError("survival JSON exceeds input budget")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result
        return json.loads(
            raw, object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("nonfinite JSON number")
            ),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid survival JSON") from exc


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-survival")
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
            source, actions = original_survival()
            result = simulate_survival(source, actions)
        elif args.command == "simulate":
            result = simulate_survival(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_survival(_json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_survival(_json(args.session_json))
        elif args.command == "export":
            result = export_survival(_json(args.session_json))
        else:
            result = import_survival(_json(args.bundle_json))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
