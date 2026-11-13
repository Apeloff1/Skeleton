"""Playable NPC itineraries and dialogue consequences over canonical scene travel.

Authored NPCs occupy deterministic scenes at each tick. Talk choices award
only authored flags and reputation; scene inventory, movement and endings
remain owned by the replay-verified scene engine. No executable NPC scripts.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance as advance_scene, _id, _limit, _object,
    new_session, normalize_world, original_demo, verify_session,
)

SCHEMA = "skeleton.scene_npc_encounter.v1"
BUNDLE_SCHEMA = "skeleton.scene_npc_encounter_bundle.v1"
MAX_NPCS = 12
MAX_ROUTE = 16
MAX_OFFERS = 4
MAX_ENDINGS = 12
MAX_ACTIONS = 96
MAX_SOURCE_BYTES = 128 * 1024
MAX_SAVE_BYTES = 2 * 1024 * 1024


def _size(payload: Any, maximum: int) -> None:
    try:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid NPC encounter JSON") from exc
    if len(data) > maximum:
        raise SceneTravelError("NPC encounter JSON size budget exceeded")


def _ids(raw: Any, label: str, maximum: int) -> list[str]:
    if type(raw) is not list or len(raw) > maximum:
        raise SceneTravelError(f"invalid {label} list")
    ids = [_id(value, label) for value in raw]
    if len(set(ids)) != len(ids):
        raise SceneTravelError(f"duplicate {label}")
    return sorted(ids)


def normalize_encounter(raw: Any) -> dict[str, Any]:
    _size(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {"schema_version", "encounter_id", "world",
                        "npcs", "endings"}, "NPC encounter source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported NPC encounter schema")
    encounter_id = _id(obj["encounter_id"], "encounter_id")
    world = normalize_world(obj["world"])
    playable = {s["id"] for s in world["scenes"] if s["ending"] is None}
    raw_npcs = obj["npcs"]
    if type(raw_npcs) is not list or not 1 <= len(raw_npcs) <= MAX_NPCS:
        raise SceneTravelError("invalid NPC encounter count")
    npcs = []
    all_flags: set[str] = set()
    for entry in raw_npcs:
        npc = _object(entry, {"id", "route", "offers"}, "NPC")
        npc_id = _id(npc["id"], "NPC id")
        route = npc["route"]
        if (type(route) is not list or not 1 <= len(route) <= MAX_ROUTE
                or any(_id(scene, "NPC route scene") not in playable
                       for scene in route)):
            raise SceneTravelError("NPC route references nonplayable scene")
        offers = npc["offers"]
        if type(offers) is not list or not 2 <= len(offers) <= MAX_OFFERS:
            raise SceneTravelError("NPC needs two to four authored choices")
        clean = []
        for offer in offers:
            item = _object(offer, {"id", "reputation", "grants_flag"}, "NPC offer")
            flag = _id(item["grants_flag"], "granted flag")
            if flag in all_flags:
                raise SceneTravelError("NPC offer flag granted twice")
            all_flags.add(flag)
            clean.append({
                "id": _id(item["id"], "offer id"),
                "reputation": _limit(item["reputation"], "reputation", -100, 100),
                "grants_flag": flag,
            })
        if len({o["id"] for o in clean}) != len(clean):
            raise SceneTravelError("duplicate NPC offer id")
        npcs.append({
            "id": npc_id, "route": list(route),
            "offers": sorted(clean, key=lambda o: o["id"]),
        })
    npcs.sort(key=lambda n: n["id"])
    if len({n["id"] for n in npcs}) != len(npcs):
        raise SceneTravelError("duplicate NPC identity")
    raw_endings = obj["endings"]
    if type(raw_endings) is not list or not 1 <= len(raw_endings) <= MAX_ENDINGS:
        raise SceneTravelError("invalid NPC encounter ending count")
    endings = []
    for entry in raw_endings:
        ending = _object(entry, {"id", "scene_phase", "requires_flags",
                                 "min_reputation"}, "NPC ending")
        phase = ending["scene_phase"]
        if type(phase) is not str or phase not in ("won", "lost", "draw"):
            raise SceneTravelError("invalid NPC ending scene phase")
        required = _ids(entry["requires_flags"], "ending flag", MAX_NPCS)
        if not set(required) <= all_flags:
            raise SceneTravelError("ending requires unauthored NPC flag")
        endings.append({
            "id": _id(ending["id"], "ending id"),
            "scene_phase": phase, "requires_flags": required,
            "min_reputation": _limit(
                ending["min_reputation"], "ending reputation", -1200, 1200,
            ),
        })
    endings.sort(key=lambda e: e["id"])
    if len({e["id"] for e in endings}) != len(endings):
        raise SceneTravelError("duplicate NPC ending id")
    return {"schema_version": SCHEMA, "encounter_id": encounter_id,
            "world": world, "npcs": npcs, "endings": endings}


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["world"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_encounter(source: Any) -> dict[str, Any]:
    spec = normalize_encounter(source)
    state = {
        "tick": 0, "scene": new_session(spec["world"]),
        "choices": {}, "flags": [], "reputation": 0,
        "phase": "active", "ending": None,
    }
    return {"schema_version": SCHEMA, "source": spec,
            "source_digest": dig(spec), "state": state,
            "state_digest": dig(state), "journal": [],
            "save": _save(spec, state)}


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise SceneTravelError("invalid NPC encounter action")
    if raw["kind"] == "scene":
        _object(raw, {"kind", "action"}, "NPC scene action")
        if type(raw["action"]) is not dict:
            raise SceneTravelError("NPC scene action must be object")
        return {"kind": "scene", "action": raw["action"]}
    if raw["kind"] == "talk":
        _object(raw, {"kind", "npc_id", "offer_id"}, "NPC talk action")
        return {"kind": "talk", "npc_id": _id(raw["npc_id"], "NPC id"),
                "offer_id": _id(raw["offer_id"], "NPC offer id")}
    if raw["kind"] == "finish":
        _object(raw, {"kind", "ending_id"}, "NPC finish action")
        return {"kind": "finish", "ending_id": _id(raw["ending_id"], "ending id")}
    raise SceneTravelError("unsupported NPC encounter action")


def _step(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active":
        raise SceneTravelError("NPC encounter already terminal")
    if old["tick"] >= MAX_ACTIONS:
        raise SceneTravelError("NPC encounter action budget exhausted")
    action = _action(raw)
    scene = old["scene"]
    choices = dict(old["choices"])
    flags = list(old["flags"])
    reputation = old["reputation"]
    phase, ending_id = "active", None
    if action["kind"] == "scene":
        scene = advance_scene(scene, action["action"])
        action = {"kind": "scene", "action": scene["journal"][-1]["action"]}
    elif action["kind"] == "talk":
        if scene["state"]["phase"] != "active":
            raise SceneTravelError("cannot talk after terminal scene")
        npc = next((n for n in source["npcs"] if n["id"] == action["npc_id"]), None)
        if npc is None or npc["route"][old["tick"] % len(npc["route"])] != scene["state"]["scene_id"]:
            raise SceneTravelError("NPC is absent at this scene and tick")
        if npc["id"] in choices:
            raise SceneTravelError("NPC already answered")
        offer = next((o for o in npc["offers"] if o["id"] == action["offer_id"]), None)
        if offer is None:
            raise SceneTravelError("NPC offer is not authored")
        choices[npc["id"]] = offer["id"]
        flags = sorted([*flags, offer["grants_flag"]])
        reputation += offer["reputation"]
    else:
        if scene["state"]["phase"] == "active":
            raise SceneTravelError("NPC ending requires terminal scene")
        ending = next((e for e in source["endings"] if e["id"] == action["ending_id"]), None)
        if ending is None or ending["scene_phase"] != scene["state"]["phase"]:
            raise SceneTravelError("NPC ending outcome not earned")
        if not set(ending["requires_flags"]) <= set(flags):
            raise SceneTravelError("NPC ending flags not earned")
        if reputation < ending["min_reputation"]:
            raise SceneTravelError("NPC ending reputation not earned")
        phase, ending_id = "finished", ending["id"]
    state = {
        "tick": old["tick"] + 1, "scene": scene,
        "choices": choices, "flags": flags, "reputation": reputation,
        "phase": phase, "ending": ending_id,
    }
    event = {
        "sequence": old["tick"], "action": action,
        "before": snapshot["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": snapshot["source_digest"], "state": state,
        "state_digest": dig(state),
        "journal": [*snapshot["journal"], event],
        "save": _save(source, state, snapshot["save"]),
    }
    _size(result, MAX_SAVE_BYTES)
    return result


def verify_encounter(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_SAVE_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "save",
    }, "NPC encounter save")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported NPC encounter save")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise SceneTravelError("invalid NPC encounter journal")
    rebuilt = new_encounter(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid NPC encounter journal event")
        rebuilt = _step(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("NPC encounter event mismatch")
    if rebuilt != obj:
        raise SceneTravelError("NPC encounter save/replay mismatch")
    return rebuilt


def resume_encounter(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_encounter(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise SceneTravelError("invalid NPC encounter action batch")
    for action in actions:
        session = _step(session, action)
    return verify_encounter(session)


def simulate_encounter(source: Any, actions: Any) -> dict[str, Any]:
    return resume_encounter(new_encounter(source), actions)


def export_encounter(payload: Any) -> dict[str, Any]:
    session = verify_encounter(payload)
    bundle = {
        "schema_version": BUNDLE_SCHEMA, "kind": "offline_npc_encounter",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _size(bundle, MAX_SAVE_BYTES)
    return bundle


def import_encounter(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_SAVE_BYTES)
    obj = _object(payload, {
        "schema_version", "kind", "source_digest",
        "state_digest", "session", "checksum",
    }, "NPC encounter bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA or obj["kind"] != "offline_npc_encounter":
        raise SceneTravelError("unsupported NPC encounter bundle")
    if type(obj["checksum"]) is not str or len(obj["checksum"]) != 64:
        raise SceneTravelError("invalid NPC encounter checksum")
    if dig({k: v for k, v in obj.items() if k != "checksum"}) != obj["checksum"]:
        raise SceneTravelError("NPC encounter checksum mismatch")
    session = verify_encounter(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise SceneTravelError("NPC encounter source/state mismatch")
    return session


def original_encounter() -> dict[str, Any]:
    world, _ = original_demo()
    return {
        "schema_version": SCHEMA, "encounter_id": "lantern_quay_contacts",
        "world": world,
        "npcs": [
            {
                "id": "quay_keeper", "route": ["quay"],
                "offers": [
                    {"id": "assist", "reputation": 3,
                     "grants_flag": "keeper_trust"},
                    {"id": "decline", "reputation": -2,
                     "grants_flag": "keeper_declined"},
                ],
            },
        ],
        "endings": [
            {"id": "rescued", "scene_phase": "won",
             "requires_flags": ["keeper_trust"], "min_reputation": 1},
            {"id": "solo", "scene_phase": "won",
             "requires_flags": [], "min_reputation": -100},
            {"id": "lost", "scene_phase": "lost",
             "requires_flags": [], "min_reputation": -100},
        ],
    }


def demo_actions() -> list[dict[str, Any]]:
    _, scene_actions = original_demo()
    return [
        {"kind": "talk", "npc_id": "quay_keeper", "offer_id": "assist"},
        *[{"kind": "scene", "action": a} for a in scene_actions],
        {"kind": "finish", "ending_id": "rescued"},
    ]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-npc")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original NPC choice and scene ending")
    sim = sub.add_parser("simulate", help="Play authored NPC scene actions")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume", help="Continue verified NPC scene save")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for name in ("verify", "export"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--session-json", required=True)
    imp = sub.add_parser("import", help="Replay-check portable NPC scene bundle")
    imp.add_argument("--bundle-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = simulate_encounter(original_encounter(), demo_actions())
        elif args.command == "simulate":
            result = simulate_encounter(
                _strict_json(args.source_json, "NPC encounter source"),
                _strict_json(args.actions_json, "NPC encounter actions"),
            )
        elif args.command == "resume":
            result = resume_encounter(
                _strict_json(args.session_json, "NPC encounter save"),
                _strict_json(args.actions_json, "NPC encounter actions"),
            )
        elif args.command == "verify":
            result = verify_encounter(_strict_json(args.session_json, "NPC encounter save"))
        elif args.command == "export":
            result = export_encounter(_strict_json(args.session_json, "NPC encounter save"))
        else:
            result = import_encounter(_strict_json(args.bundle_json, "NPC encounter bundle"))
        _size(result, MAX_SAVE_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
