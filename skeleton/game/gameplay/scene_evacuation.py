"""Deterministic, source-bound multi-person evacuation over the mission director.

The canonical mission owns scene movement, pickups, decisions and endings.
Evacuation adds timed rescue windows, limited carrying capacity, injury and
earned protection; it cannot mint mission progress or skip authored exits.
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
    _action as mission_action, _advance as advance_mission, demo_actions as mission_demo,
    new_mission, normalize_mission_world, original_mission,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_evacuation.v1"
MAX_NPCS = 16
MAX_HAZARDS = 16
MAX_TURNS = 96
MAX_BYTES = 2 * 1024 * 1024


def _bounded(value: Any) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid evacuation JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise SceneTravelError("evacuation byte budget exceeded")


def normalize_evacuation(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "evacuation_id", "mission", "npcs", "capacity",
        "required_rescues", "supplies", "hazards", "success_endings",
        "base_reward", "turn_budget",
    }, "evacuation source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported evacuation schema")
    mission = normalize_mission_world(obj["mission"])
    world = mission["world"]
    scenes = {scene["id"]: scene for scene in world["scenes"]}
    playable = {key for key, scene in scenes.items() if scene["ending"] is None}
    budget = _limit(obj["turn_budget"], "evacuation turn budget", 1, MAX_TURNS)
    raw_npcs = obj["npcs"]
    if type(raw_npcs) is not list or not 1 <= len(raw_npcs) <= MAX_NPCS:
        raise SceneTravelError("evacuation requires 1..16 authored NPCs")
    npcs = []
    for raw_npc in raw_npcs:
        npc = _object(raw_npc, {
            "id", "scene_id", "health", "available_from", "expires_at", "reward",
        }, "evacuation NPC")
        scene_id = _id(npc["scene_id"], "NPC scene")
        if scene_id not in playable:
            raise SceneTravelError("NPC must start in an authored playable scene")
        first = _limit(npc["available_from"], "NPC availability", 0, budget)
        last = _limit(npc["expires_at"], "NPC expiry", 0, budget)
        if first > last:
            raise SceneTravelError("NPC availability starts after expiry")
        npcs.append({
            "id": _id(npc["id"], "NPC id"), "scene_id": scene_id,
            "health": _limit(npc["health"], "NPC health", 1, 9),
            "available_from": first, "expires_at": last,
            "reward": _limit(npc["reward"], "NPC reward", 0, 100),
        })
    if len({npc["id"] for npc in npcs}) != len(npcs):
        raise SceneTravelError("duplicate evacuation NPC")
    capacity = _limit(obj["capacity"], "rescue capacity", 1, MAX_NPCS)
    required = _limit(obj["required_rescues"], "required rescues", 1, MAX_NPCS)
    if capacity > len(npcs) or required > capacity:
        raise SceneTravelError("evacuation target exceeds carrying capacity")
    pickups = {
        scene["id"] + ":" + pickup["id"]
        for scene in world["scenes"] for pickup in scene["pickups"]
    }
    raw_supplies = obj["supplies"]
    if type(raw_supplies) is not list or len(raw_supplies) > 16:
        raise SceneTravelError("invalid evacuation supply count")
    supplies = [_id(item, "evacuation supply") for item in raw_supplies]
    if len(set(supplies)) != len(supplies) or not set(supplies) <= pickups:
        raise SceneTravelError("supplies must be distinct canonical pickups")
    raw_hazards = obj["hazards"]
    if type(raw_hazards) is not list or len(raw_hazards) > MAX_HAZARDS:
        raise SceneTravelError("invalid evacuation hazard count")
    hazards = []
    for raw_hazard in raw_hazards:
        hazard = _object(raw_hazard, {"scene_id", "damage"}, "evacuation hazard")
        scene_id = _id(hazard["scene_id"], "hazard scene")
        if scene_id not in playable:
            raise SceneTravelError("hazards must reference playable scenes")
        hazards.append({
            "scene_id": scene_id,
            "damage": _limit(hazard["damage"], "hazard damage", 0, 9),
        })
    if len({h["scene_id"] for h in hazards}) != len(hazards):
        raise SceneTravelError("duplicate evacuation hazard")
    raw_endings = obj["success_endings"]
    possible = {e["id"] for e in mission["endings"] if e["scene_phase"] == "won"}
    if type(raw_endings) is not list or not 1 <= len(raw_endings) <= 8:
        raise SceneTravelError("invalid evacuation success endings")
    endings = [_id(item, "evacuation ending") for item in raw_endings]
    if len(set(endings)) != len(endings) or not set(endings) <= possible:
        raise SceneTravelError("evacuation success ending is not authored victory")
    result = {
        "schema_version": SCHEMA,
        "evacuation_id": _id(obj["evacuation_id"], "evacuation id"),
        "mission": mission, "npcs": sorted(npcs, key=lambda x: x["id"]),
        "capacity": capacity, "required_rescues": required,
        "supplies": sorted(supplies),
        "hazards": sorted(hazards, key=lambda x: x["scene_id"]),
        "success_endings": sorted(endings),
        "base_reward": _limit(obj["base_reward"], "base reward", 0, 10000),
        "turn_budget": budget,
    }
    _bounded(result)
    return result


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["mission"]["world"]["world_id"],
        schema_version=1, tick=state["tick"],
        state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(index, "evacuation.action", event["action"]["kind"], event["receipt"])
        for index, event in enumerate(journal)
    )).digest


def new_evacuation(raw: Any) -> dict[str, Any]:
    source = normalize_evacuation(raw)
    state = {
        "tick": 0, "mission": new_mission(source["mission"]),
        "passengers": [], "rescued": [], "lost": [], "supplies": 0,
        "shielded": False, "phase": "active", "reward": 0,
    }
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(source, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid evacuation action")
    kind = raw.get("kind")
    if kind in ("wait", "protect"):
        _object(raw, {"kind"}, "evacuation action")
        return {"kind": kind}
    if kind == "rescue":
        _object(raw, {"kind", "npc_id"}, "rescue action")
        return {"kind": kind, "npc_id": _id(raw["npc_id"], "rescued NPC")}
    if kind == "mission":
        _object(raw, {"kind", "action"}, "evacuation mission action")
        return {"kind": kind, "action": mission_action(raw["action"])}
    raise SceneTravelError("unsupported evacuation action")


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise SceneTravelError("evacuation already terminal")
    if old["tick"] >= source["turn_budget"]:
        raise SceneTravelError("evacuation turn budget exhausted")
    action = _action(raw)
    state = {
        **old, "tick": old["tick"] + 1,
        "passengers": [dict(p) for p in old["passengers"]],
        "rescued": list(old["rescued"]), "lost": list(old["lost"]),
    }
    scene = old["mission"]["state"]["scene"]["state"]["scene_id"]
    if action["kind"] == "rescue":
        npc = next((n for n in source["npcs"] if n["id"] == action["npc_id"]), None)
        if (npc is None or npc["scene_id"] != scene
                or npc["id"] in old["rescued"] or npc["id"] in old["lost"]
                or not npc["available_from"] <= old["tick"] <= npc["expires_at"]):
            raise SceneTravelError("NPC is not available for rescue at this scene")
        if old["mission"]["state"]["scene"]["state"]["phase"] != "active":
            raise SceneTravelError("cannot rescue after scene is terminal")
        if len(old["passengers"]) >= source["capacity"]:
            raise SceneTravelError("evacuation carrying capacity exhausted")
        state["passengers"].append({"id": npc["id"], "health": npc["health"]})
        state["passengers"].sort(key=lambda p: p["id"])
        state["rescued"].append(npc["id"])
        state["rescued"].sort()
    elif action["kind"] == "protect":
        if old["supplies"] < 1 or old["shielded"]:
            raise SceneTravelError("protection requires an earned unused supply")
        state["supplies"] -= 1
        state["shielded"] = True
    elif action["kind"] == "mission":
        before = old["mission"]["state"]["scene"]["state"]
        mission = advance_mission(old["mission"], action["action"])
        after = mission["state"]["scene"]["state"]
        state["mission"] = mission
        gained = set(after["collected"]) - set(before["collected"])
        state["supplies"] += len(gained & set(source["supplies"]))
        if before["scene_id"] != after["scene_id"]:
            damage = next((h["damage"] for h in source["hazards"]
                           if h["scene_id"] == after["scene_id"]), 0)
            if old["shielded"]:
                damage = max(0, damage - 1)
            survivors = []
            for passenger in state["passengers"]:
                remaining = passenger["health"] - damage
                if remaining > 0:
                    survivors.append({"id": passenger["id"], "health": remaining})
                else:
                    state["lost"].append(passenger["id"])
            state["passengers"] = survivors
            state["shielded"] = False
        if mission["state"]["phase"] == "finished":
            if (mission["state"]["ending"] in source["success_endings"]
                    and len(state["passengers"]) >= source["required_rescues"]):
                state["phase"] = "evacuated"
                reward_ids = {p["id"] for p in state["passengers"]}
                state["reward"] = source["base_reward"] + sum(
                    npc["reward"] for npc in source["npcs"] if npc["id"] in reward_ids
                )
            else:
                state["phase"] = "partial"
    # Expiration is deterministic; late NPCs cannot be rescued retroactively.
    for npc in source["npcs"]:
        if (npc["expires_at"] < state["tick"]
                and npc["id"] not in state["rescued"]
                and npc["id"] not in state["lost"]):
            state["lost"].append(npc["id"])
    state["lost"].sort()
    if state["phase"] == "active" and state["tick"] >= source["turn_budget"]:
        state["phase"] = "expired"
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": journal, "event_bus_digest": _bus(journal),
        "save": _save(source, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_evacuation(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state", "state_digest",
        "journal", "event_bus_digest", "save",
    }, "evacuation checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported evacuation checkpoint schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_TURNS:
        raise SceneTravelError("evacuation journal exceeds turn budget")
    rebuilt = new_evacuation(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid evacuation journal event")
        try:
            rebuilt = _advance(rebuilt, event["action"])
        except (KeyError, TypeError, RecursionError) as exc:
            raise SceneTravelError("malformed evacuation replay action") from exc
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("evacuation replay receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("evacuation checkpoint source/state mismatch")
    return rebuilt


def advance_evacuation(raw: Any, action: Any) -> dict[str, Any]:
    return _advance(verify_evacuation(raw), action)


def simulate_evacuation(source: Any, actions: Any, *,
                        resume: Any = None) -> dict[str, Any]:
    if type(actions) is not list or len(actions) > MAX_TURNS:
        raise SceneTravelError("invalid evacuation action batch")
    session = new_evacuation(source) if resume is None else verify_evacuation(resume)
    if session["source_digest"] != dig(normalize_evacuation(source)):
        raise SceneTravelError("evacuation resume source mismatch")
    if len(actions) + len(session["journal"]) > session["source"]["turn_budget"]:
        raise SceneTravelError("evacuation action budget exceeded")
    for action in actions:
        session = _advance(session, action)
    return verify_evacuation(session)


def resume_evacuation(checkpoint: Any, actions: Any) -> dict[str, Any]:
    verified = verify_evacuation(checkpoint)
    return simulate_evacuation(verified["source"], actions, resume=verified)


def export_evacuation(raw: Any) -> dict[str, Any]:
    return export_verified(raw, kind="scene_evacuation", verifier=verify_evacuation)


def import_evacuation(raw: Any) -> dict[str, Any]:
    return import_verified(raw, kind="scene_evacuation", verifier=verify_evacuation)


def original_evacuation() -> dict[str, Any]:
    mission = original_mission()
    mission["world"]["scenes"][0]["pickups"].append({
        "id": "find_bandage", "item_id": "field_bandage",
    })
    return {
        "schema_version": SCHEMA, "evacuation_id": "lantern_tide_rescue",
        "mission": mission, "capacity": 2, "required_rescues": 2,
        "npcs": [
            {"id": "dock_apprentice", "scene_id": "quay", "health": 2,
             "available_from": 0, "expires_at": 8, "reward": 12},
            {"id": "watch_keeper", "scene_id": "gate", "health": 2,
             "available_from": 0, "expires_at": 12, "reward": 18},
        ],
        "supplies": ["quay:find_bandage"],
        "hazards": [{"scene_id": "gate", "damage": 1}],
        "success_endings": ["lantern_restored"], "base_reward": 30,
        "turn_budget": 20,
    }


def demo_actions() -> list[dict[str, Any]]:
    mission_actions = mission_demo()
    return [
        {"kind": "mission", "action": mission_actions[0]},
        {"kind": "mission", "action": {"kind": "scene", "action": {
            "kind": "collect", "pickup_id": "find_bandage",
        }}},
        {"kind": "rescue", "npc_id": "dock_apprentice"},
        {"kind": "mission", "action": mission_actions[1]},
        {"kind": "protect"},
        {"kind": "mission", "action": mission_actions[2]},
        {"kind": "rescue", "npc_id": "watch_keeper"},
        {"kind": "mission", "action": mission_actions[3]},
        {"kind": "mission", "action": mission_actions[4]},
    ]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-evacuation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("accept")
    sim = sub.add_parser("simulate")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for name in ("verify", "export"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        parse = lambda text: _strict_json(text, "evacuation JSON", max_bytes=MAX_BYTES)
        if args.command == "demo":
            result = simulate_evacuation(original_evacuation(), demo_actions())
        elif args.command == "accept":
            from skeleton.game.gameplay.scene_evacuation_acceptance import accept_evacuation
            result = accept_evacuation(original_evacuation(), demo_actions())
        elif args.command == "simulate":
            result = simulate_evacuation(parse(args.source_json), parse(args.actions_json))
        elif args.command == "resume":
            result = resume_evacuation(parse(args.session_json), parse(args.actions_json))
        elif args.command in ("verify", "export"):
            checkpoint = parse(args.session_json)
            result = (verify_evacuation(checkpoint) if args.command == "verify"
                      else export_evacuation(checkpoint))
        else:
            result = import_evacuation(parse(args.bundle_json))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
