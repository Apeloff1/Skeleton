"""Source-bound offline expedition quests, NPC schedules and crafting.

This is a canonical gameplay adapter over the tactical expedition runtime.
Only replayed authored actions may change inventory, dialogue or endings.
Digests detect corruption; they are not signatures or author authorization.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_expedition import (
    _advance as advance_expedition,
    new_expedition,
    normalize_expedition,
    original_expedition,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.expedition_quest.v1"
BUNDLE_SCHEMA = "skeleton.expedition_quest_bundle.v1"
MAX_LOCATIONS = 12
MAX_NPCS = 12
MAX_RECIPES = 16
MAX_ENDINGS = 8
MAX_ACTIONS = 96
MAX_ITEMS = 32
MAX_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 128 * 1024


def _size(value: Any, limit: int) -> None:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("quest JSON is not canonical") from exc
    if len(encoded) > limit:
        raise CombatSessionError("quest JSON size budget exceeded")


def _ids(raw: Any, label: str, maximum: int) -> list[str]:
    if type(raw) is not list or len(raw) > maximum:
        raise CombatSessionError(f"invalid {label} list")
    values = [_id(value, label) for value in raw]
    if len(set(values)) != len(values):
        raise CombatSessionError(f"duplicate {label}")
    return values


def normalize_quest(raw: Any) -> dict[str, Any]:
    """Validate every author-controlled reference and bounded game resource."""
    _size(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {
        "schema_version", "world_id", "quest_id", "expedition",
        "locations", "start_location", "camp_location",
        "workshop_location", "npcs", "recipes", "endings",
    }, "quest source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported quest source schema")
    world = _id(obj["world_id"], "world_id")
    quest_id = _id(obj["quest_id"], "quest_id")
    expedition = normalize_expedition(obj["expedition"])
    if expedition["world_id"] != world:
        raise CombatSessionError("quest expedition world mismatch")
    raw_locations = obj["locations"]
    if type(raw_locations) is not list or not 1 <= len(raw_locations) <= MAX_LOCATIONS:
        raise CombatSessionError("invalid quest location count")
    locations = []
    for entry in raw_locations:
        place = _object(entry, {"id", "exits"}, "quest location")
        locations.append({
            "id": _id(place["id"], "location_id"),
            "exits": _ids(place["exits"], "location exit", MAX_LOCATIONS),
        })
    locations.sort(key=lambda p: p["id"])
    place_ids = {p["id"] for p in locations}
    if len(place_ids) != len(locations):
        raise CombatSessionError("duplicate quest location")
    for place in locations:
        if place["id"] in place["exits"] or not set(place["exits"]) <= place_ids:
            raise CombatSessionError("invalid quest location exit")
    start = _id(obj["start_location"], "start_location")
    camp = _id(obj["camp_location"], "camp_location")
    workshop = _id(obj["workshop_location"], "workshop_location")
    if not {start, camp, workshop} <= place_ids:
        raise CombatSessionError("quest location reference missing")
    reachable = {start}
    while True:
        discovered = reachable | {
            dest for p in locations if p["id"] in reachable for dest in p["exits"]
        }
        if discovered == reachable:
            break
        reachable = discovered
    if reachable != place_ids:
        raise CombatSessionError("quest contains unreachable locations")

    raw_npcs = obj["npcs"]
    if type(raw_npcs) is not list or len(raw_npcs) > MAX_NPCS:
        raise CombatSessionError("invalid NPC count")
    npcs = []
    for entry in raw_npcs:
        npc = _object(entry, {"id", "route", "gift"}, "quest NPC")
        route = _ids(npc["route"], "NPC route location", MAX_LOCATIONS)
        if not route or not set(route) <= place_ids:
            raise CombatSessionError("NPC route location missing")
        npcs.append({
            "id": _id(npc["id"], "npc_id"),
            "route": route, "gift": _id(npc["gift"], "gift_item"),
        })
    npcs.sort(key=lambda npc: npc["id"])
    if len({npc["id"] for npc in npcs}) != len(npcs):
        raise CombatSessionError("duplicate NPC id")
    npc_ids = {npc["id"] for npc in npcs}

    raw_recipes = obj["recipes"]
    if type(raw_recipes) is not list or len(raw_recipes) > MAX_RECIPES:
        raise CombatSessionError("invalid recipe count")
    recipes = []
    for entry in raw_recipes:
        recipe = _object(entry, {"id", "inputs", "output"}, "quest recipe")
        ingredients = _ids(recipe["inputs"], "ingredient", MAX_ITEMS)
        if not ingredients:
            raise CombatSessionError("recipe needs ingredients")
        output = _id(recipe["output"], "crafted_item")
        if output in ingredients:
            raise CombatSessionError("recipe cannot consume its own output")
        recipes.append({
            "id": _id(recipe["id"], "recipe_id"),
            "inputs": sorted(ingredients), "output": output,
        })
    recipes.sort(key=lambda recipe: recipe["id"])
    if len({r["id"] for r in recipes}) != len(recipes):
        raise CombatSessionError("duplicate recipe id")
    if len({r["output"] for r in recipes}) != len(recipes):
        raise CombatSessionError("duplicate crafted output")
    gifts = {npc["gift"] for npc in npcs}
    available = set(gifts)
    remaining = list(recipes)
    while remaining:
        ready = [r for r in remaining if set(r["inputs"]) <= available]
        if not ready:
            raise CombatSessionError("recipe inputs unavailable or cyclic")
        for recipe in ready:
            available.add(recipe["output"])
            remaining.remove(recipe)

    raw_endings = obj["endings"]
    if type(raw_endings) is not list or not 1 <= len(raw_endings) <= MAX_ENDINGS:
        raise CombatSessionError("invalid ending count")
    endings = []
    for entry in raw_endings:
        ending = _object(entry, {"id", "outcome", "choices", "items"}, "quest ending")
        if ending["outcome"] not in ("won", "lost", "draw"):
            raise CombatSessionError("invalid ending outcome")
        choices = []
        if type(ending["choices"]) is not list or len(ending["choices"]) > MAX_NPCS:
            raise CombatSessionError("invalid ending choice count")
        for choice in ending["choices"]:
            c = _object(choice, {"npc_id", "decision"}, "ending choice")
            npc_id = _id(c["npc_id"], "npc_id")
            if npc_id not in npc_ids or c["decision"] not in ("aid", "decline"):
                raise CombatSessionError("invalid ending choice requirement")
            choices.append({"npc_id": npc_id, "decision": c["decision"]})
        if len({c["npc_id"] for c in choices}) != len(choices):
            raise CombatSessionError("duplicate ending choice requirement")
        items = _ids(ending["items"], "ending item", MAX_ITEMS)
        if not set(items) <= available:
            raise CombatSessionError("ending item cannot be obtained")
        endings.append({
            "id": _id(ending["id"], "ending_id"),
            "outcome": ending["outcome"],
            "choices": sorted(choices, key=lambda c: c["npc_id"]),
            "items": sorted(items),
        })
    endings.sort(key=lambda ending: ending["id"])
    if len({e["id"] for e in endings}) != len(endings):
        raise CombatSessionError("duplicate ending id")
    return {
        "schema_version": SCHEMA, "world_id": world, "quest_id": quest_id,
        "expedition": expedition, "locations": locations,
        "start_location": start, "camp_location": camp,
        "workshop_location": workshop, "npcs": npcs,
        "recipes": recipes, "endings": endings,
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["world_id"], schema_version=1, tick=state["tick"],
        state_digest=dig(state), canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_quest(source: Any) -> dict[str, Any]:
    spec = normalize_quest(source)
    state = {
        "tick": 0, "location": spec["start_location"],
        "choices": {}, "items": {}, "crafted": [],
        "expedition": new_expedition(spec["expedition"]),
        "phase": "active", "ending": None,
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise CombatSessionError("invalid quest action")
    kind = raw["kind"]
    fields = {
        "travel": {"kind", "to"},
        "talk": {"kind", "npc_id", "decision"},
        "craft": {"kind", "recipe_id"},
        "expedition": {"kind", "action"},
        "finish": {"kind", "ending_id"},
        "wait": {"kind"},
    }
    if kind not in fields:
        raise CombatSessionError("unsupported quest action")
    _object(raw, fields[kind], "quest action")
    if kind == "travel":
        return {"kind": kind, "to": _id(raw["to"], "destination")}
    if kind == "talk":
        if raw["decision"] not in ("aid", "decline"):
            raise CombatSessionError("invalid NPC decision")
        return {
            "kind": kind, "npc_id": _id(raw["npc_id"], "npc_id"),
            "decision": raw["decision"],
        }
    if kind == "craft":
        return {"kind": kind, "recipe_id": _id(raw["recipe_id"], "recipe_id")}
    if kind == "finish":
        return {"kind": kind, "ending_id": _id(raw["ending_id"], "ending_id")}
    if kind == "expedition":
        if type(raw["action"]) is not dict:
            raise CombatSessionError("invalid embedded expedition action")
        return {"kind": kind, "action": raw["action"]}
    return {"kind": "wait"}


def _event_bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "quest.action", entry["action"]["kind"], entry["receipt"])
        for i, entry in enumerate(journal)
    )).digest


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise CombatSessionError("quest already terminal")
    if old["tick"] >= MAX_ACTIONS:
        raise CombatSessionError("quest action budget exhausted")
    action = _action(raw)
    state = {
        **old, "tick": old["tick"] + 1,
        "choices": dict(old["choices"]), "items": dict(old["items"]),
        "crafted": list(old["crafted"]),
    }
    kind = action["kind"]
    if kind == "travel":
        location = next(p for p in source["locations"] if p["id"] == old["location"])
        if action["to"] not in location["exits"]:
            raise CombatSessionError("destination is not an authored exit")
        state["location"] = action["to"]
    elif kind == "talk":
        npc = next((n for n in source["npcs"] if n["id"] == action["npc_id"]), None)
        if npc is None or npc["route"][old["tick"] % len(npc["route"])] != old["location"]:
            raise CombatSessionError("NPC is not present at this location and tick")
        if npc["id"] in state["choices"]:
            raise CombatSessionError("NPC decision already recorded")
        state["choices"][npc["id"]] = action["decision"]
        if action["decision"] == "aid":
            if sum(state["items"].values()) >= MAX_ITEMS:
                raise CombatSessionError("quest inventory full")
            gift = npc["gift"]
            state["items"][gift] = state["items"].get(gift, 0) + 1
    elif kind == "craft":
        if old["location"] != source["workshop_location"]:
            raise CombatSessionError("crafting requires the authored workshop")
        recipe = next(
            (r for r in source["recipes"] if r["id"] == action["recipe_id"]), None
        )
        if recipe is None or recipe["id"] in state["crafted"]:
            raise CombatSessionError("recipe unavailable or already crafted")
        if any(state["items"].get(item, 0) < 1 for item in recipe["inputs"]):
            raise CombatSessionError("insufficient earned ingredients")
        for item in recipe["inputs"]:
            state["items"][item] -= 1
            if state["items"][item] == 0:
                del state["items"][item]
        state["items"][recipe["output"]] = state["items"].get(recipe["output"], 0) + 1
        state["crafted"].append(recipe["id"])
    elif kind == "expedition":
        if old["location"] != source["camp_location"]:
            raise CombatSessionError("combat expedition requires the authored camp")
        state["expedition"] = advance_expedition(old["expedition"], action["action"])
    elif kind == "finish":
        ending = next(
            (e for e in source["endings"] if e["id"] == action["ending_id"]), None
        )
        if ending is None or old["expedition"]["state"]["phase"] != ending["outcome"]:
            raise CombatSessionError("ending outcome not earned")
        if any(
            state["choices"].get(c["npc_id"]) != c["decision"]
            for c in ending["choices"]
        ):
            raise CombatSessionError("ending choice consequence not satisfied")
        if any(state["items"].get(item, 0) < 1 for item in ending["items"]):
            raise CombatSessionError("ending required item not earned")
        state["phase"] = "finished"
        state["ending"] = ending["id"]
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
        "journal": journal, "event_bus_digest": _event_bus(journal),
        "save": _save(source, state, session["save"]),
    }
    _size(result, MAX_BYTES)
    return result


def verify_quest(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "quest session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported quest session schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise CombatSessionError("invalid quest journal")
    rebuilt = new_quest(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid quest event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("quest journal receipt mismatch")
    if rebuilt != obj:
        raise CombatSessionError("quest save or replay mismatch")
    return rebuilt


def resume_quest(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_quest(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise CombatSessionError("invalid quest action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_quest(source: Any, actions: Any) -> dict[str, Any]:
    return resume_quest(new_quest(source), actions)


def export_quest(payload: Any) -> dict[str, Any]:
    session = verify_quest(payload)
    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _size(bundle, MAX_BYTES)
    return bundle


def import_quest(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "quest bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA:
        raise CombatSessionError("unsupported quest bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("quest bundle checksum mismatch")
    session = verify_quest(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise CombatSessionError("quest bundle source/state mismatch")
    return session


def original_quest() -> dict[str, Any]:
    """Original Lantern Harbor supply-beacon patrol, playable without network."""
    return {
        "schema_version": SCHEMA, "world_id": "lantern_harbor",
        "quest_id": "lantern_beacon", "expedition": original_expedition(),
        "locations": [
            {"id": "dock", "exits": ["forge", "camp"]},
            {"id": "forge", "exits": ["dock"]},
            {"id": "camp", "exits": ["dock"]},
        ],
        "start_location": "dock", "camp_location": "camp",
        "workshop_location": "forge",
        "npcs": [
            {"id": "guide", "route": ["dock"], "gift": "reed"},
            {"id": "smith", "route": ["forge"], "gift": "ore"},
        ],
        "recipes": [{"id": "beacon", "inputs": ["ore", "reed"],
                     "output": "signal_beacon"}],
        "endings": [
            {"id": "beacon_lit", "outcome": "won",
             "choices": [{"npc_id": "guide", "decision": "aid"},
                         {"npc_id": "smith", "decision": "aid"}],
             "items": ["signal_beacon"]},
            {"id": "quiet_victory", "outcome": "won",
             "choices": [], "items": []},
            {"id": "lost_patrol", "outcome": "lost",
             "choices": [], "items": []},
            {"id": "drawn_patrol", "outcome": "draw",
             "choices": [], "items": []},
        ],
    }


def demo_actions() -> list[dict[str, Any]]:
    return [
        {"kind": "talk", "npc_id": "guide", "decision": "aid"},
        {"kind": "travel", "to": "forge"},
        {"kind": "talk", "npc_id": "smith", "decision": "aid"},
        {"kind": "craft", "recipe_id": "beacon"},
        {"kind": "travel", "to": "dock"},
        {"kind": "travel", "to": "camp"},
        {"kind": "expedition", "action": {"kind": "fight"}},
        {"kind": "expedition", "action": {"kind": "buy", "item_id": "tide_tonic"}},
        {"kind": "expedition", "action": {"kind": "use", "item_id": "tide_tonic"}},
        {"kind": "expedition", "action": {"kind": "fight"}},
        {"kind": "finish", "ending_id": "beacon_lit"},
    ]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-expedition")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run the original offline beacon quest")
    sim = sub.add_parser("simulate", help="Simulate authored quest actions")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume", help="Continue a verified quest save")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify", help="Replay and verify an offline save")
    verify.add_argument("--session-json", required=True)
    export = sub.add_parser("export", help="Create a portable checksum bundle")
    export.add_argument("--session-json", required=True)
    imported = sub.add_parser("import", help="Verify a portable checksum bundle")
    imported.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = simulate_quest(original_quest(), demo_actions())
        elif args.command == "simulate":
            result = simulate_quest(
                _parse_json(args.source_json, "quest source"),
                _parse_json(args.actions_json, "quest actions"),
            )
        elif args.command == "resume":
            result = resume_quest(
                _parse_json(args.session_json, "quest session"),
                _parse_json(args.actions_json, "quest actions"),
            )
        elif args.command == "verify":
            result = verify_quest(_parse_json(args.session_json, "quest session"))
        elif args.command == "export":
            result = export_quest(_parse_json(args.session_json, "quest session"))
        else:
            result = import_quest(_parse_json(args.bundle_json, "quest bundle"))
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
