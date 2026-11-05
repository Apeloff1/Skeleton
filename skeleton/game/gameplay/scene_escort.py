"""Source-bound convoy escort over the canonical scene mission runtime.

Escort supplies come only from canonical pickups. Damage follows authored
scene transitions, and terminal rewards require a replay-proven mission ending.
No authored Python callbacks, external services, or implicit inventory grants.
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
from skeleton.game.gameplay.offline_portable import export_verified, import_verified
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_mission import (
    _action as mission_action, _advance as advance_mission,
    demo_actions as mission_demo_actions, new_mission,
    normalize_mission_world, original_mission,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_escort.v1"
MAX_ACTIONS = 256
MAX_BYTES = 2 * 1024 * 1024
MAX_SUPPLY_PICKUPS = 32
MAX_HAZARDS = 32


def _bounded(value: Any) -> None:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid escort JSON") from exc
    if len(data) > MAX_BYTES:
        raise SceneTravelError("escort payload exceeds byte budget")


def normalize_escort_source(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "convoy_id", "mission", "destination_scene",
        "max_integrity", "travel_damage", "supply_pickups", "hazards",
        "delivery_reward", "turn_budget",
    }, "escort source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported escort source schema")
    mission = normalize_mission_world(obj["mission"])
    world = mission["world"]
    scene_ids = {scene["id"] for scene in world["scenes"]}
    destination = _id(obj["destination_scene"], "escort destination")
    if destination not in scene_ids or destination == world["start_scene"]:
        raise SceneTravelError("escort destination must be another authored scene")
    pickup_ids = {
        scene["id"] + ":" + pickup["id"]
        for scene in world["scenes"] for pickup in scene["pickups"]
    }
    raw_supplies = obj["supply_pickups"]
    if type(raw_supplies) is not list or len(raw_supplies) > MAX_SUPPLY_PICKUPS:
        raise SceneTravelError("invalid escort supply count")
    supplies = [_id(value, "escort supply pickup") for value in raw_supplies]
    if len(set(supplies)) != len(supplies) or not set(supplies) <= pickup_ids:
        raise SceneTravelError("escort supplies must be unique authored pickups")
    raw_hazards = obj["hazards"]
    if type(raw_hazards) is not list or len(raw_hazards) > MAX_HAZARDS:
        raise SceneTravelError("invalid escort hazard count")
    hazards = []
    for item in raw_hazards:
        hazard = _object(item, {"scene_id", "damage"}, "escort hazard")
        scene_id = _id(hazard["scene_id"], "escort hazard scene")
        if scene_id not in scene_ids:
            raise SceneTravelError("escort hazard references missing scene")
        hazards.append({
            "scene_id": scene_id,
            "damage": _limit(hazard["damage"], "escort hazard damage", 0, 9),
        })
    if len({h["scene_id"] for h in hazards}) != len(hazards):
        raise SceneTravelError("duplicate escort hazard scene")
    return {
        "schema_version": SCHEMA, "convoy_id": _id(obj["convoy_id"], "convoy id"),
        "mission": mission, "destination_scene": destination,
        "max_integrity": _limit(obj["max_integrity"], "convoy integrity", 1, 100),
        "travel_damage": _limit(obj["travel_damage"], "travel damage", 0, 9),
        "supply_pickups": sorted(supplies),
        "hazards": sorted(hazards, key=lambda h: h["scene_id"]),
        "delivery_reward": _limit(obj["delivery_reward"], "delivery reward", 0, 10000),
        "turn_budget": _limit(obj["turn_budget"], "escort turn budget", 1, MAX_ACTIONS),
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["mission"]["world"]["world_id"],
        schema_version=1, tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(index, "escort.action", event["action"]["kind"], event["receipt"])
        for index, event in enumerate(journal)
    )).digest


def new_escort(source: Any) -> dict[str, Any]:
    spec = normalize_escort_source(source)
    state = {
        "tick": 0, "mission": new_mission(spec["mission"]),
        "integrity": spec["max_integrity"], "supplies": 0,
        "shielded": False, "phase": "active", "reward": 0,
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid escort action")
    if raw.get("kind") == "protect":
        _object(raw, {"kind"}, "escort protect action")
        return {"kind": "protect"}
    if raw.get("kind") == "mission":
        _object(raw, {"kind", "action"}, "escort mission action")
        return {"kind": "mission", "action": mission_action(raw["action"])}
    raise SceneTravelError("unsupported escort action")


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old, spec = session["state"], session["source"]
    if old["phase"] != "active":
        raise SceneTravelError("escort already terminal")
    if old["tick"] >= spec["turn_budget"]:
        raise SceneTravelError("escort turn budget exhausted")
    action = _action(raw)
    state = {**old, "tick": old["tick"] + 1}
    if action["kind"] == "protect":
        if old["supplies"] < 1 or old["shielded"]:
            raise SceneTravelError("escort protection requires earned unused supply")
        state["supplies"] -= 1
        state["shielded"] = True
    else:
        before = old["mission"]["state"]["scene"]["state"]
        mission = advance_mission(old["mission"], action["action"])
        after = mission["state"]["scene"]["state"]
        state["mission"] = mission
        newly_collected = set(after["collected"]) - set(before["collected"])
        state["supplies"] += len(newly_collected & set(spec["supply_pickups"]))
        if before["scene_id"] != after["scene_id"]:
            hazard = next(
                (item["damage"] for item in spec["hazards"]
                 if item["scene_id"] == after["scene_id"]), 0
            )
            damage = spec["travel_damage"] + hazard
            if old["shielded"]:
                damage = max(0, damage - 1)
            state["integrity"] = max(0, old["integrity"] - damage)
            state["shielded"] = False
            if state["integrity"] == 0:
                state["phase"] = "lost"
        if mission["state"]["phase"] == "finished" and state["phase"] == "active":
            if (after["scene_id"] == spec["destination_scene"]
                    and after["phase"] == "won"):
                state["phase"] = "delivered"
                state["reward"] = spec["delivery_reward"]
            else:
                state["phase"] = "lost"
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": journal, "event_bus_digest": _bus(journal),
        "save": _save(spec, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_escort(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state", "state_digest",
        "journal", "event_bus_digest", "save",
    }, "escort session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported escort session schema")
    events = obj["journal"]
    if type(events) is not list or len(events) > MAX_ACTIONS:
        raise SceneTravelError("invalid escort journal")
    rebuilt = new_escort(obj["source"])
    for event in events:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid escort journal event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("escort replay event mismatch")
    if rebuilt != obj:
        raise SceneTravelError("escort source or save mismatch")
    return rebuilt


def simulate_escort(source: Any, actions: Any) -> dict[str, Any]:
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise SceneTravelError("invalid escort action batch")
    session = new_escort(source)
    for action in actions:
        session = _advance(session, action)
    return verify_escort(session)


def resume_escort(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_escort(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise SceneTravelError("invalid escort resume batch")
    for action in actions:
        session = _advance(session, action)
    return verify_escort(session)


def export_escort(payload: Any) -> dict[str, Any]:
    return export_verified(payload, kind="scene_escort", verifier=verify_escort)


def import_escort(payload: Any) -> dict[str, Any]:
    return import_verified(payload, kind="scene_escort", verifier=verify_escort)


def original_escort() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "convoy_id": "lantern_caravan",
        "mission": original_mission(), "destination_scene": "sanctuary",
        "max_integrity": 2, "travel_damage": 1,
        "supply_pickups": ["quay:find_key"], "hazards": [],
        "delivery_reward": 20, "turn_budget": 32,
    }


def demo_actions() -> list[dict[str, Any]]:
    mission_actions = mission_demo_actions()
    return [
        {"kind": "mission", "action": mission_actions[0]},
        {"kind": "mission", "action": mission_actions[1]},
        {"kind": "protect"},
        *({"kind": "mission", "action": item} for item in mission_actions[2:]),
    ]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-escort")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sim = sub.add_parser("simulate")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    export = sub.add_parser("export")
    export.add_argument("--session-json", required=True)
    imported = sub.add_parser("import")
    imported.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        parse = lambda raw: _strict_json(raw, "escort JSON", max_bytes=MAX_BYTES)
        if args.command == "demo":
            result = simulate_escort(original_escort(), demo_actions())
        elif args.command == "simulate":
            result = simulate_escort(parse(args.source_json), parse(args.actions_json))
        elif args.command == "resume":
            result = resume_escort(parse(args.session_json), parse(args.actions_json))
        elif args.command == "verify":
            result = verify_escort(parse(args.session_json))
        elif args.command == "export":
            result = export_escort(parse(args.session_json))
        else:
            result = import_escort(parse(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
