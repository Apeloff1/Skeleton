"""Offline tactical arena expedition with earned rewards, healing and replay.

Source-authored arenas use the canonical tactical engine. Player purchases,
item consumption, combat outcomes and checkpoint lineage are reconstructed
from ordered actions, never trusted from client-supplied reward fields.
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
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)
from skeleton.game.gameplay.tactical_arena import (
    normalize_arena, original_arena,
)
from skeleton.game.gameplay.arena_policy import run_autoplay

SCHEMA = "skeleton.arena_expedition.v1"
MAX_ARENAS = 6
MAX_ITEMS = 12
MAX_ACTIONS = 96
MAX_CURRENCY = 100000
MAX_INVENTORY = 16


def normalize_expedition(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "expedition_id", "world_id", "hero_id",
        "hero_team", "arenas", "shop",
    }, "expedition")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported expedition schema")
    world_id = _id(obj["world_id"], "world_id")
    expedition_id = _id(obj["expedition_id"], "expedition_id")
    hero_id = _id(obj["hero_id"], "hero_id")
    hero_team = _id(obj["hero_team"], "hero_team")
    raw_arenas = obj["arenas"]
    if type(raw_arenas) is not list or not 1 <= len(raw_arenas) <= MAX_ARENAS:
        raise CombatSessionError("invalid expedition arena count")
    arenas = []
    ids = set()
    baseline = None
    for entry in raw_arenas:
        _object(entry, {"arena", "reward"}, "expedition arena")
        arena = normalize_arena(entry["arena"])
        if arena["world_id"] != world_id:
            raise CombatSessionError("expedition world identity mismatch")
        if arena["arena_id"] in ids:
            raise CombatSessionError("duplicate expedition arena")
        ids.add(arena["arena_id"])
        heroes = [a for a in arena["actors"] if a["id"] == hero_id]
        if len(heroes) != 1 or heroes[0]["team"] != hero_team:
            raise CombatSessionError("hero identity mismatch")
        if sum(a["team"] == hero_team for a in arena["actors"]) != 1:
            raise CombatSessionError("expedition requires one hero-team actor")
        stable = {key: heroes[0][key] for key in (
            "id", "team", "max_hp", "attack", "defense", "speed", "range",
        )}
        if baseline is None:
            baseline = stable
        elif baseline != stable:
            raise CombatSessionError("hero baseline changes between arenas")
        if arena["turn_limit"] > 64:
            raise CombatSessionError("expedition arena turn budget exceeded")
        arenas.append({
            "arena": arena,
            "reward": _integer(entry["reward"], "reward", 0, MAX_CURRENCY),
        })
    if sum(a["reward"] for a in arenas) > MAX_CURRENCY:
        raise CombatSessionError("expedition reward budget exceeded")
    raw_shop = obj["shop"]
    if type(raw_shop) is not list or len(raw_shop) > MAX_ITEMS:
        raise CombatSessionError("invalid expedition shop")
    shop = []
    seen = set()
    for entry in raw_shop:
        _object(entry, {"id", "price", "heal", "stock"}, "shop item")
        item_id = _id(entry["id"], "item_id")
        if item_id in seen:
            raise CombatSessionError("duplicate shop item")
        seen.add(item_id)
        shop.append({
            "id": item_id,
            "price": _integer(entry["price"], "price", 1, MAX_CURRENCY),
            "heal": _integer(entry["heal"], "heal", 1, 10000),
            "stock": _integer(entry["stock"], "stock", 1, MAX_INVENTORY),
        })
    shop.sort(key=lambda x: x["id"])
    return {
        "schema_version": SCHEMA, "expedition_id": expedition_id,
        "world_id": world_id, "hero_id": hero_id, "hero_team": hero_team,
        "arenas": arenas, "shop": shop,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_expedition(source: Any) -> dict[str, Any]:
    spec = normalize_expedition(source)
    hero = next(
        actor for actor in spec["arenas"][0]["arena"]["actors"]
        if actor["id"] == spec["hero_id"]
    )
    state = {
        "tick": 0, "next_index": 0, "hero_hp": hero["max_hp"],
        "currency": 0, "phase": "active", "inventory": {},
        "purchased": {}, "arenas": [],
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest,
        "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid expedition action")
    kind = raw.get("kind")
    if type(kind) is not str or kind not in ("fight", "buy", "use"):
        raise CombatSessionError("unsupported expedition action")
    required = {"kind"} if kind == "fight" else {"kind", "item_id"}
    _object(raw, required, "expedition action")
    return (
        {"kind": kind} if kind == "fight"
        else {"kind": kind, "item_id": _id(raw["item_id"], "item_id")}
    )


def _event_digest(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "expedition.action", event["action"]["kind"],
                      event["receipt"])
        for i, event in enumerate(journal)
    )).digest


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise CombatSessionError("expedition already terminal")
    if old["tick"] >= MAX_ACTIONS:
        raise CombatSessionError("expedition action budget exceeded")
    action = _action(raw)
    state = {
        **old, "tick": old["tick"] + 1,
        "inventory": dict(old["inventory"]),
        "purchased": dict(old["purchased"]),
        "arenas": list(old["arenas"]),
    }
    outcome = None
    if action["kind"] == "fight":
        index = state["next_index"]
        if index >= len(source["arenas"]):
            raise CombatSessionError("no remaining arena")
        entry = source["arenas"][index]
        arena = json.loads(json.dumps(entry["arena"]))
        hero = next(a for a in arena["actors"] if a["id"] == source["hero_id"])
        hero["max_hp"] = state["hero_hp"]
        if hero["max_hp"] < 1:
            raise CombatSessionError("hero cannot fight with zero health")
        result = run_autoplay(arena)
        remaining = result["state"]["actors"][source["hero_id"]]["hp"]
        victory = (
            result["state"]["phase"] == "won"
            and result["state"]["winner"] == source["hero_team"]
        )
        reward = entry["reward"] if victory else 0
        state["currency"] += reward
        if state["currency"] > MAX_CURRENCY:
            raise CombatSessionError("expedition currency overflow")
        state["hero_hp"] = remaining
        state["next_index"] = index + 1
        state["arenas"].append({
            "arena_id": arena["arena_id"], "reward": reward,
            "session": result,
        })
        if not victory:
            state["phase"] = "lost" if remaining == 0 else "draw"
        elif state["next_index"] == len(source["arenas"]):
            state["phase"] = "won"
        outcome = {
            "arena_id": arena["arena_id"], "reward": reward,
            "combat_state_digest": result["state_digest"],
            "combat_event_bus_digest": result["event_bus_digest"],
        }
    else:
        items = {item["id"]: item for item in source["shop"]}
        item_id = action["item_id"]
        if item_id not in items:
            raise CombatSessionError("unknown shop item")
        item = items[item_id]
        if action["kind"] == "buy":
            if state["currency"] < item["price"]:
                raise CombatSessionError("insufficient earned currency")
            if state["purchased"].get(item_id, 0) >= item["stock"]:
                raise CombatSessionError("shop stock exhausted")
            if sum(state["inventory"].values()) >= MAX_INVENTORY:
                raise CombatSessionError("inventory full")
            state["currency"] -= item["price"]
            state["purchased"][item_id] = state["purchased"].get(item_id, 0) + 1
            state["inventory"][item_id] = state["inventory"].get(item_id, 0) + 1
        else:
            if state["inventory"].get(item_id, 0) <= 0:
                raise CombatSessionError("item not owned")
            hero_max = next(
                actor for actor in source["arenas"][0]["arena"]["actors"]
                if actor["id"] == source["hero_id"]
            )["max_hp"]
            if state["hero_hp"] >= hero_max:
                raise CombatSessionError("hero already at full health")
            state["hero_hp"] = min(hero_max, state["hero_hp"] + item["heal"])
            state["inventory"][item_id] -= 1
            if state["inventory"][item_id] == 0:
                del state["inventory"][item_id]
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
        "outcome": outcome,
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": journal, "event_bus_digest": _event_digest(journal),
        "save": _save(source, state, session["save"]),
    }


def verify_expedition(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "expedition session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported expedition save schema")
    rebuilt = new_expedition(obj["source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise CombatSessionError("invalid expedition journal")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid expedition event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("expedition event mismatch")
    if rebuilt != obj:
        raise CombatSessionError("expedition save or replay mismatch")
    return rebuilt


def resume_expedition(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_expedition(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise CombatSessionError("invalid expedition action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_expedition(source: Any, actions: Any) -> dict[str, Any]:
    return resume_expedition(new_expedition(source), actions)


def original_expedition() -> dict[str, Any]:
    """Original Lantern Harbor two-arena patrol and consumable supply stop."""
    first = original_arena()
    first["arena_id"] = "canal_watch"
    first["width"] = 5
    first["walls"] = []
    first["actors"][1]["position"] = [4, 1]
    first["actors"][1]["max_hp"] = 12
    first["actors"][1]["attack"] = 5
    first["turn_limit"] = 24
    second = json.loads(json.dumps(first))
    second["arena_id"] = "tide_gate"
    second["actors"][1]["id"] = "mireling"
    second["actors"][1]["attack"] = 4
    second["actors"][1]["max_hp"] = 7
    return {
        "schema_version": SCHEMA, "expedition_id": "lantern_patrol",
        "world_id": "lantern_harbor", "hero_id": "scout",
        "hero_team": "wayfarers",
        "arenas": [
            {"arena": first, "reward": 10},
            {"arena": second, "reward": 20},
        ],
        "shop": [
            {"id": "tide_tonic", "price": 5, "heal": 6, "stock": 2},
        ],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-expedition")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run original two-arena campaign with earned rewards")
    sim = sub.add_parser("simulate", help="Run authored purchases, healing and fights")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify", help="Replay-check expedition save and rewards")
    verify.add_argument("--session-json", required=True)
    resume = sub.add_parser("resume", help="Continue source-bound expedition")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = simulate_expedition(
                original_expedition(),
                [{"kind": "fight"}, {"kind": "buy", "item_id": "tide_tonic"},
                 {"kind": "use", "item_id": "tide_tonic"}, {"kind": "fight"}],
            )
        elif args.command == "simulate":
            result = simulate_expedition(
                _parse_json(args.source_json, "expedition source"),
                _parse_json(args.actions_json, "expedition actions"),
            )
        elif args.command == "verify":
            result = verify_expedition(_parse_json(args.session_json, "expedition save"))
        else:
            result = resume_expedition(
                _parse_json(args.session_json, "expedition save"),
                _parse_json(args.actions_json, "expedition actions"),
            )
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
            raise CombatSessionError("expedition output budget exceeded")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
