"""Offline arena salvage, equipment forging, deterministic replay and portable saves."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)
from skeleton.game.gameplay.tactical_arena import (
    normalize_arena, original_arena, verify_arena, _action as arena_action,
)
from skeleton.game.gameplay.arena_policy import run_autoplay
from skeleton.game.gameplay.arena_player_policy import run_player_tactics

SCHEMA = "skeleton.arena_forge_run.v1"
BUNDLE = "skeleton.arena_forge_bundle.v1"
MAX_ACTIONS = 96
MAX_MATERIALS = 128
MAX_BYTES = 2 * 1024 * 1024


def _entries(raw: Any, name: str, maximum: int) -> list[dict[str, Any]]:
    if type(raw) is not list or len(raw) > maximum:
        raise CombatSessionError(f"invalid {name} count")
    items = []
    seen = set()
    for value in raw:
        entry = _object(value, {"id", "quantity"}, name)
        key = _id(entry["id"], name + " id")
        if key in seen:
            raise CombatSessionError(f"duplicate {name} id")
        seen.add(key)
        items.append({"id": key, "quantity": _integer(
            entry["quantity"], name + " quantity", 1, 16,
        )})
    return sorted(items, key=lambda x: x["id"])


def normalize_forge(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "run_id", "world_id", "hero_id",
                        "hero_team", "stages", "recipes"}, "forge source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported forge schema")
    run_id = _id(obj["run_id"], "run_id")
    world = _id(obj["world_id"], "world_id")
    hero_id = _id(obj["hero_id"], "hero_id")
    hero_team = _id(obj["hero_team"], "hero_team")
    if type(obj["stages"]) is not list or not 1 <= len(obj["stages"]) <= 6:
        raise CombatSessionError("invalid forge stage count")
    stages, ids, materials, baseline = [], set(), set(), None
    for raw_stage in obj["stages"]:
        stage = _object(raw_stage, {"arena", "drops"}, "forge stage")
        arena = normalize_arena(stage["arena"])
        if arena["world_id"] != world or arena["arena_id"] in ids:
            raise CombatSessionError("forge arena identity mismatch")
        ids.add(arena["arena_id"])
        if arena["turn_limit"] > 64:
            raise CombatSessionError("forge arena turn budget exceeded")
        heroes = [a for a in arena["actors"] if a["id"] == hero_id]
        if len(heroes) != 1 or heroes[0]["team"] != hero_team:
            raise CombatSessionError("forge hero identity mismatch")
        if sum(a["team"] == hero_team for a in arena["actors"]) != 1:
            raise CombatSessionError("forge requires one hero-team actor")
        stats = {k: heroes[0][k] for k in (
            "id", "team", "max_hp", "attack", "defense", "speed", "range",
        )}
        if baseline is not None and baseline != stats:
            raise CombatSessionError("forge hero baseline mismatch")
        baseline = stats
        drops = _entries(stage["drops"], "drop", 8)
        materials.update(x["id"] for x in drops)
        stages.append({"arena": arena, "drops": drops})
    if sum(x["quantity"] for s in stages for x in s["drops"]) > MAX_MATERIALS:
        raise CombatSessionError("forge drop budget exceeded")
    if type(obj["recipes"]) is not list or not 1 <= len(obj["recipes"]) <= 12:
        raise CombatSessionError("invalid forge recipe count")
    recipes, recipe_ids = [], set()
    for raw_recipe in obj["recipes"]:
        recipe = _object(raw_recipe, {"id", "costs", "attack_bonus",
                                      "defense_bonus", "durability"}, "forge recipe")
        key = _id(recipe["id"], "recipe id")
        if key in recipe_ids:
            raise CombatSessionError("duplicate forge recipe")
        recipe_ids.add(key)
        costs = _entries(recipe["costs"], "cost", 8)
        if not costs or any(x["id"] not in materials for x in costs):
            raise CombatSessionError("forge recipe requires earned materials")
        attack = _integer(recipe["attack_bonus"], "attack bonus", 0, 100)
        defense = _integer(recipe["defense_bonus"], "defense bonus", 0, 100)
        if not (attack or defense):
            raise CombatSessionError("forge recipe must improve combat")
        if baseline["attack"] + attack > 1000 or baseline["defense"] + defense > 1000:
            raise CombatSessionError("forge bonus exceeds combat bounds")
        recipes.append({"id": key, "costs": costs, "attack_bonus": attack,
                        "defense_bonus": defense, "durability": _integer(
                            recipe["durability"], "durability", 1, 6,
                        )})
    return {"schema_version": SCHEMA, "run_id": run_id, "world_id": world,
            "hero_id": hero_id, "hero_team": hero_team, "stages": stages,
            "recipes": sorted(recipes, key=lambda x: x["id"])}


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1, tick=state["tick"],
        state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _events(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(GameplayEvent(
        i, "arena.forge", entry["action"]["kind"], entry["receipt"],
    ) for i, entry in enumerate(journal))).digest


def new_forge(source: Any) -> dict[str, Any]:
    spec = normalize_forge(source)
    hero = next(a for a in spec["stages"][0]["arena"]["actors"]
                if a["id"] == spec["hero_id"])
    state = {"tick": 0, "next_index": 0, "hero_hp": hero["max_hp"],
             "phase": "active", "materials": {}, "gear": {},
             "equipped": None, "fights": []}
    return {"schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
            "state": state, "state_digest": dig(state), "journal": [],
            "event_bus_digest": EventBus().digest, "save": _save(spec, state)}


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid forge action")
    kind = raw.get("kind")
    if kind in ("fight", "unequip"):
        _object(raw, {"kind"}, "forge action")
        return {"kind": kind}
    if kind == "fight_tactical":
        _object(raw, {"kind", "hero_actions"}, "forge action")
        moves = raw["hero_actions"]
        if type(moves) is not list or len(moves) > 64:
            raise CombatSessionError("invalid tactical action budget")
        return {"kind": kind, "hero_actions": [arena_action(m) for m in moves]}
    if kind in ("craft", "equip"):
        _object(raw, {"kind", "recipe_id"}, "forge action")
        return {"kind": kind, "recipe_id": _id(raw["recipe_id"], "recipe_id")}
    raise CombatSessionError("unsupported forge action")


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active" or old["tick"] >= MAX_ACTIONS:
        raise CombatSessionError("forge run terminal or action budget exceeded")
    action = _action(raw)
    state = {**old, "tick": old["tick"] + 1,
             "materials": dict(old["materials"]), "gear": dict(old["gear"]),
             "fights": list(old["fights"])}
    outcome = None
    if action["kind"] in ("fight", "fight_tactical"):
        index = state["next_index"]
        if index >= len(source["stages"]) or state["hero_hp"] <= 0:
            raise CombatSessionError("no playable forge stage")
        stage = source["stages"][index]
        arena = json.loads(json.dumps(stage["arena"]))
        hero = next(a for a in arena["actors"] if a["id"] == source["hero_id"])
        hero["max_hp"] = state["hero_hp"]
        used = state["equipped"]
        if used is not None:
            if state["gear"].get(used, 0) <= 0:
                raise CombatSessionError("equipped forge gear not owned")
            recipe = next(r for r in source["recipes"] if r["id"] == used)
            hero["attack"] += recipe["attack_bonus"]
            hero["defense"] += recipe["defense_bonus"]
        combat = verify_arena(
            run_autoplay(arena) if action["kind"] == "fight"
            else run_player_tactics(arena, source["hero_id"], action["hero_actions"])
        )
        hp = combat["state"]["actors"][source["hero_id"]]["hp"]
        victory = (combat["state"]["phase"] == "won"
                   and combat["state"]["winner"] == source["hero_team"])
        if victory:
            for drop in stage["drops"]:
                key = drop["id"]
                state["materials"][key] = state["materials"].get(key, 0) + drop["quantity"]
            if sum(state["materials"].values()) > MAX_MATERIALS:
                raise CombatSessionError("forge material capacity exceeded")
        if used is not None:
            state["gear"][used] -= 1
            if state["gear"][used] == 0:
                del state["gear"][used]
                state["equipped"] = None
        state["next_index"] += 1
        state["hero_hp"] = hp
        if not victory:
            state["phase"] = "lost" if hp == 0 else "draw"
        elif state["next_index"] == len(source["stages"]):
            state["phase"] = "won"
        state["fights"].append({"arena_id": arena["arena_id"], "equipped": used,
                                "victory": victory, "combat": combat})
        outcome = {"arena_id": arena["arena_id"], "victory": victory,
                   "combat_state_digest": combat["state_digest"]}
    elif action["kind"] == "craft":
        recipe = next((r for r in source["recipes"]
                       if r["id"] == action["recipe_id"]), None)
        if recipe is None:
            raise CombatSessionError("unknown forge recipe")
        if recipe["id"] in state["gear"]:
            raise CombatSessionError("forge gear already owned")
        for cost in recipe["costs"]:
            if state["materials"].get(cost["id"], 0) < cost["quantity"]:
                raise CombatSessionError("insufficient earned forge materials")
        for cost in recipe["costs"]:
            key = cost["id"]
            remaining = state["materials"][key] - cost["quantity"]
            if remaining:
                state["materials"][key] = remaining
            else:
                del state["materials"][key]
        state["gear"][recipe["id"]] = recipe["durability"]
    elif action["kind"] == "equip":
        key = action["recipe_id"]
        if state["gear"].get(key, 0) <= 0:
            raise CombatSessionError("forge gear not owned")
        state["equipped"] = key
    else:
        state["equipped"] = None
    event = {"sequence": old["tick"], "action": action,
             "before": session["state_digest"], "after": dig(state),
             "outcome": outcome}
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    return {"schema_version": SCHEMA, "source": source,
            "source_digest": session["source_digest"], "state": state,
            "state_digest": dig(state), "journal": journal,
            "event_bus_digest": _events(journal),
            "save": _save(source, state, session["save"])}


def verify_forge(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "source", "source_digest", "state",
                            "state_digest", "journal", "event_bus_digest", "save"},
                  "forge session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported forge save")
    rebuilt = new_forge(obj["source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise CombatSessionError("invalid forge journal")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid forge event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("forge action replay mismatch")
    if rebuilt != obj:
        raise CombatSessionError("forge state or save lineage mismatch")
    return rebuilt


def resume_forge(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_forge(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise CombatSessionError("invalid forge action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_forge(source: Any, actions: Any) -> dict[str, Any]:
    return resume_forge(new_forge(source), actions)


def export_forge(payload: Any) -> dict[str, Any]:
    session = verify_forge(payload)
    result = {"schema_version": BUNDLE, "session": session,
              "session_digest": dig(session)}
    if len(json.dumps(result, sort_keys=True, allow_nan=False).encode()) > MAX_BYTES:
        raise CombatSessionError("forge bundle budget exceeded")
    return result


def import_forge(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "session", "session_digest"},
                  "forge bundle")
    if obj["schema_version"] != BUNDLE or dig(obj["session"]) != obj["session_digest"]:
        raise CombatSessionError("forge bundle identity mismatch")
    return verify_forge(obj["session"])


def original_forge() -> dict[str, Any]:
    first = original_arena()
    first["arena_id"] = "lantern_salvage"
    first["actors"][1]["max_hp"] = 3
    second = json.loads(json.dumps(first))
    second["arena_id"] = "tide_forge_gate"
    second["actors"][1]["id"] = "tide_guard"
    second["actors"][1]["max_hp"] = 24
    second["actors"][1]["defense"] = 4
    return {"schema_version": SCHEMA, "run_id": "lantern_forge",
            "world_id": "lantern_harbor", "hero_id": "scout",
            "hero_team": "wayfarers",
            "stages": [
                {"arena": first, "drops": [{"id": "tide_iron", "quantity": 2}]},
                {"arena": second, "drops": [{"id": "tide_iron", "quantity": 1}]},
            ],
            "recipes": [{"id": "tide_edge",
                         "costs": [{"id": "tide_iron", "quantity": 2}],
                         "attack_bonus": 5, "defense_bonus": 1, "durability": 2}]}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-forge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name, options in {
        "preview": ("source-json",),
        "simulate": ("source-json", "actions-json"),
        "resume": ("session-json", "actions-json"),
        "verify": ("session-json",),
        "export": ("session-json",),
        "import": ("bundle-json",),
    }.items():
        command = sub.add_parser(name)
        for option in options:
            command.add_argument("--" + option, required=True)
    args = parser.parse_args(list(argv))
    try:
        read = lambda name: _parse_json(getattr(args, name.replace("-", "_")), name)
        if args.command == "demo":
            result = simulate_forge(original_forge(), [
                {"kind": "fight"}, {"kind": "craft", "recipe_id": "tide_edge"},
                {"kind": "equip", "recipe_id": "tide_edge"}, {"kind": "fight"},
            ])
        elif args.command == "preview":
            result = normalize_forge(read("source-json"))
        elif args.command == "simulate":
            result = simulate_forge(read("source-json"), read("actions-json"))
        elif args.command == "resume":
            result = resume_forge(read("session-json"), read("actions-json"))
        elif args.command == "verify":
            result = verify_forge(read("session-json"))
        elif args.command == "export":
            result = export_forge(read("session-json"))
        else:
            result = import_forge(read("bundle-json"))
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            raise CombatSessionError("forge output budget exceeded")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
