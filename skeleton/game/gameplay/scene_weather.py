"""Deterministic authored weather and earned protection over playable survival.

Only the canonical survival reducer can collect items, move through walls, cross
exits, rest or resolve the underlying ending. This overlay applies bounded
environmental pressure, never mints canonical resources, and reconstructs every
checkpoint by replaying the original authored source and action journal.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_walk import MAX_BYTES, MAX_STEPS, _bounded, _json
from skeleton.game.gameplay.scene_tile_survival import (
    _advance as advance_survival, new_survival, normalize_survival,
    original_survival, verify_survival,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_weather.v1"
BUNDLE = "skeleton.scene_weather_bundle.v1"
MAX_PHASES = 8
MAX_GEAR = 32
MAX_SOURCE_BYTES = 256 * 1024
KINDS = ("clear", "rain", "frost", "heat", "storm")


def normalize_weather(raw: Any) -> dict[str, Any]:
    """Validate weather, equipment provenance and all finite resource budgets."""
    _bounded(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {
        "schema_version", "survival_source", "max_stamina", "turn_limit",
        "climates", "gear",
    }, "weather source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather schema")
    survival = normalize_survival(obj["survival_source"])
    stamina = _limit(obj["max_stamina"], "max stamina", 1, 64)
    limit = _limit(obj["turn_limit"], "weather turn limit", 1, MAX_STEPS)
    areas = {area["scene_id"] for area in survival["tile_source"]["maps"]}
    climates = obj["climates"]
    if type(climates) is not list or not 1 <= len(climates) <= len(areas):
        raise SceneTravelError("invalid weather climate count")
    clean_climates = []
    seen = set()
    for raw_climate in climates:
        climate = _object(raw_climate, {"scene_id", "phases"}, "climate")
        scene = _id(climate["scene_id"], "climate scene")
        if scene not in areas or scene in seen:
            raise SceneTravelError("unknown or duplicate climate scene")
        seen.add(scene)
        phases = climate["phases"]
        if type(phases) is not list or not 1 <= len(phases) <= MAX_PHASES:
            raise SceneTravelError("invalid weather phase count")
        clean_phases = []
        for raw_phase in phases:
            phase = _object(raw_phase, {
                "kind", "damage", "stamina_cost",
            }, "weather phase")
            if type(phase["kind"]) is not str or phase["kind"] not in KINDS:
                raise SceneTravelError("unsupported weather condition")
            damage = _limit(phase["damage"], "weather damage", 0, 8)
            cost = _limit(phase["stamina_cost"], "weather stamina cost", 0, 8)
            if phase["kind"] == "clear" and (damage or cost):
                raise SceneTravelError("clear weather cannot inflict a penalty")
            clean_phases.append({
                "kind": phase["kind"], "damage": damage, "stamina_cost": cost,
            })
        clean_climates.append({"scene_id": scene, "phases": clean_phases})
    # Every authored map gets explicit deterministic climate; no silent defaults.
    if seen != areas:
        raise SceneTravelError("every tile scene requires a climate")
    pickups = {
        area["scene_id"] + ":" + pickup["id"]
        for area in survival["tile_source"]["maps"]
        for pickup in area["pickups"]
    }
    gear = obj["gear"]
    if type(gear) is not list or len(gear) > MAX_GEAR:
        raise SceneTravelError("invalid equipment count")
    clean_gear = []
    gear_ids = set()
    pickup_ids = set()
    for raw_gear in gear:
        item = _object(raw_gear, {
            "gear_id", "pickup", "protects", "damage_reduction",
            "stamina_reduction",
        }, "equipment")
        ident = _id(item["gear_id"], "equipment id")
        pickup = _id(item["pickup"], "equipment pickup")
        if ident in gear_ids or pickup in pickup_ids or pickup not in pickups:
            raise SceneTravelError("duplicate or unearned equipment pickup")
        gear_ids.add(ident)
        pickup_ids.add(pickup)
        protects = item["protects"]
        if (type(protects) is not list or not 1 <= len(protects) <= len(KINDS)
                or any(type(k) is not str or k not in KINDS or k == "clear"
                       for k in protects) or len(set(protects)) != len(protects)):
            raise SceneTravelError("invalid equipment weather protection")
        clean_gear.append({
            "gear_id": ident, "pickup": pickup,
            "protects": sorted(protects),
            "damage_reduction": _limit(
                item["damage_reduction"], "equipment damage reduction", 0, 8),
            "stamina_reduction": _limit(
                item["stamina_reduction"], "equipment stamina reduction", 0, 8),
        })
    return {
        "schema_version": SCHEMA, "survival_source": survival,
        "max_stamina": stamina, "turn_limit": limit,
        "climates": sorted(clean_climates, key=lambda c: c["scene_id"]),
        "gear": sorted(clean_gear, key=lambda g: g["gear_id"]),
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_digest": dig(source), "state_digest": dig(state),
        "tick": state["tick"],
        "parent_save_digest": dig(parent) if parent is not None else None,
    }


def new_weather(source: Any) -> dict[str, Any]:
    spec = normalize_weather(source)
    survival = new_survival(spec["survival_source"])
    state = {
        "tick": 0, "survival": survival, "health": survival["state"]["health"],
        "stamina": spec["max_stamina"], "owned_gear": [], "equipped": None,
        "phase": "active",
    }
    result = {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "save": _save(spec, state),
    }
    _bounded(result)
    return result


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid weather action")
    kind = raw.get("kind")
    if kind == "survival":
        _object(raw, {"kind", "action"}, "weather survival action")
        if type(raw["action"]) is not dict or raw["action"].get("kind") not in ("tile", "rest"):
            raise SceneTravelError("invalid nested survival action")
        return {"kind": "survival", "action": raw["action"]}
    if kind == "equip":
        _object(raw, {"kind", "gear_id"}, "weather equipment action")
        return {"kind": "equip", "gear_id": _id(raw["gear_id"], "gear id")}
    if kind == "unequip":
        _object(raw, {"kind"}, "weather unequip action")
        return {"kind": "unequip"}
    raise SceneTravelError("unsupported weather action")


def forecast(source: dict[str, Any], scene_id: str, tick: int) -> dict[str, Any]:
    """A pure source-bound weather clock, independent of wall time or RNG."""
    _limit(tick, "weather forecast tick", 1, MAX_STEPS)
    climate = next(
        (c for c in source["climates"] if c["scene_id"] == scene_id), None)
    if climate is None:
        raise SceneTravelError("weather forecast scene is not authored")
    return climate["phases"][(tick - 1) % len(climate["phases"])]


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old, source = session["state"], session["source"]
    if old["phase"] != "active" or old["tick"] >= source["turn_limit"]:
        raise SceneTravelError("weather session already terminal")
    action = _action(raw)
    state = {
        "tick": old["tick"] + 1, "survival": old["survival"],
        "health": old["health"], "stamina": old["stamina"],
        "owned_gear": list(old["owned_gear"]), "equipped": old["equipped"],
        "phase": "active",
    }
    if action["kind"] == "equip":
        if action["gear_id"] not in old["owned_gear"]:
            raise SceneTravelError("equipment has not been earned")
        if old["equipped"] == action["gear_id"]:
            raise SceneTravelError("equipment is already equipped")
        state["equipped"] = action["gear_id"]
    elif action["kind"] == "unequip":
        if old["equipped"] is None:
            raise SceneTravelError("no equipment is equipped")
        state["equipped"] = None
    else:
        nested = action["action"]
        before_survival = old["survival"]["state"]
        before_tile = before_survival["tile"]["state"]
        if nested["kind"] == "tile" and nested["action"].get("kind") == "move":
            scene_id = before_tile["scene"]["state"]["scene_id"]
            weather = forecast(source, scene_id, state["tick"])
            gear = next(
                (g for g in source["gear"] if g["gear_id"] == old["equipped"]), None)
            protected = gear is not None and weather["kind"] in gear["protects"]
            cost = 1 + max(0, weather["stamina_cost"] -
                           (gear["stamina_reduction"] if protected else 0))
            if old["stamina"] < cost:
                raise SceneTravelError("insufficient earned stamina for movement")
            # Canonical collision is checked before overlay consequences.
            state["survival"] = advance_survival(old["survival"], nested)
            state["stamina"] -= cost
            penalty = max(0, weather["damage"] -
                          (gear["damage_reduction"] if protected else 0))
            hazard = max(0, before_survival["health"] -
                         state["survival"]["state"]["health"])
            state["health"] = max(0, old["health"] - hazard - penalty)
        else:
            state["survival"] = advance_survival(old["survival"], nested)
            change = state["survival"]["state"]["health"] - before_survival["health"]
            state["health"] = min(
                source["survival_source"]["max_health"],
                max(0, old["health"] + change))
            if nested["kind"] == "rest":
                state["stamina"] = source["max_stamina"]
            if nested["kind"] == "tile" and nested["action"].get("kind") == "collect":
                collected_before = set(before_tile["scene"]["state"]["collected"])
                after_tile = state["survival"]["state"]["tile"]["state"]
                collected_after = set(after_tile["scene"]["state"]["collected"])
                gained = collected_after - collected_before
                owned = set(state["owned_gear"])
                owned.update(
                    item["gear_id"] for item in source["gear"]
                    if item["pickup"] in gained)
                state["owned_gear"] = sorted(owned)
    if state["health"] == 0:
        state["phase"] = "lost"
    elif state["survival"]["state"]["phase"] != "active":
        state["phase"] = state["survival"]["state"]["phase"]
    elif state["tick"] >= source["turn_limit"]:
        state["phase"] = "draw"
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": [*session["journal"], event],
        "save": _save(source, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_weather(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state", "state_digest",
        "journal", "save",
    }, "weather session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather session schema")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid weather journal")
    rebuilt = new_weather(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid weather replay event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("weather replay receipt mismatch")
    if rebuilt != obj or verify_survival(rebuilt["state"]["survival"]) != rebuilt["state"]["survival"]:
        raise SceneTravelError("weather save or source lineage mismatch")
    return rebuilt


def resume_weather(payload: Any, actions: Any) -> dict[str, Any]:
    current = verify_weather(payload)
    if (type(actions) is not list or
            len(actions) + len(current["journal"]) > MAX_STEPS):
        raise SceneTravelError("invalid weather action batch")
    for action in actions:
        current = _advance(current, action)
    return current


def simulate_weather(source: Any, actions: Any) -> dict[str, Any]:
    return resume_weather(new_weather(source), actions)


def export_weather(payload: Any) -> dict[str, Any]:
    session = verify_weather(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_weather(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "weather bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported weather bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("weather bundle checksum mismatch")
    session = verify_weather(obj["session"])
    if (obj["source_digest"] != session["source_digest"] or
            obj["state_digest"] != session["state_digest"]):
        raise SceneTravelError("weather bundle source/state mismatch")
    return session


def original_weather() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    survival, actions = original_survival()
    climates = [
        {"scene_id": area["scene_id"], "phases": [
            {"kind": "clear", "damage": 0, "stamina_cost": 0},
        ]}
        for area in survival["tile_source"]["maps"]
    ]
    for entry in climates:
        if entry["scene_id"] == "quay":
            entry["phases"] = [
                {"kind": "rain", "damage": 0, "stamina_cost": 1},
                {"kind": "frost", "damage": 1, "stamina_cost": 0},
            ]
    source = {
        "schema_version": SCHEMA, "survival_source": survival,
        "max_stamina": 20, "turn_limit": 32,
        "climates": climates,
        "gear": [{
            "gear_id": "stormcloak", "pickup": "quay:find_key",
            "protects": ["rain", "frost"], "damage_reduction": 1,
            "stamina_reduction": 1,
        }],
    }
    sequence = [{"kind": "survival", "action": a} for a in actions]
    sequence.insert(2, {"kind": "equip", "gear_id": "stormcloak"})
    return source, sequence


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather")
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
            source, actions = original_weather()
            result = simulate_weather(source, actions)
        elif args.command == "simulate":
            result = simulate_weather(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_weather(_json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_weather(_json(args.session_json))
        elif args.command == "export":
            result = export_weather(_json(args.session_json))
        else:
            result = import_weather(_json(args.bundle_json))
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
