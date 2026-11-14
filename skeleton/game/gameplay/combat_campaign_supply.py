"""Replay-verified between-encounter supplies for authored offline combat.

Only canonical combat determines victory, health and earned currency. Players
can spend *earned* currency on a bounded medkit or one-use defensive ward;
each command is replayed from authored source before a checkpoint is trusted.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import (
    MAX_CURRENCY, finish_campaign, normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_supply.v1"
PACKAGE_SCHEMA = "skeleton.combat_campaign_supply_package.v1"
MAX_COMMANDS = 40
MAX_INVENTORY = 3
WARD_DEFENSE = 2


def _encoded(value: Any) -> str:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise CombatSessionError("invalid supply JSON") from exc
    if len(result.encode("utf-8")) > MAX_CLI_BYTES:
        raise CombatSessionError("supply save exceeds 128 KiB")
    return result


def normalize_supply(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "campaign", "prices"}, "supply source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported supply source schema")
    prices = _object(obj["prices"], {"medkit", "ward"}, "supply prices")
    return {
        "schema_version": SCHEMA,
        "campaign": normalize_campaign(obj["campaign"]),
        "prices": {
            item: _integer(prices[item], item + " price", 1, MAX_CURRENCY)
            for item in ("medkit", "ward")
        },
    }


def _hero_max(spec: dict[str, Any]) -> int:
    campaign = spec["campaign"]
    return next(a["max_hp"] for a in campaign["encounters"][0]["scenario"]["actors"]
                if a["id"] == campaign["hero_id"])


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["campaign"]["world_id"], schema_version=1,
        tick=len(state["journal"]), state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _snapshot(source: dict[str, Any], state: dict[str, Any],
              parent: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "source": source, "source_digest": dig(source),
        "state": state, "state_digest": dig(state),
        "save": _save(source, state, parent),
    }
    _encoded(result)
    return result


def new_supply(raw: Any) -> dict[str, Any]:
    source = normalize_supply(raw)
    state = {
        "phase": "active", "encounter_index": 0, "hp": _hero_max(source),
        "currency": 0, "inventory": {"medkit": 0, "ward": 0},
        "ward_active": False, "journal": [], "battles": [],
    }
    return _snapshot(source, state)


def _command(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid supply command")
    kind = raw.get("kind")
    if kind == "fight":
        _object(raw, {"kind"}, "fight command")
        return {"kind": "fight"}
    if kind in ("buy", "use"):
        obj = _object(raw, {"kind", "item"}, "supply command")
        item = _id(obj["item"], "supply item")
        if item not in ("medkit", "ward"):
            raise CombatSessionError("unsupported supply item")
        return {"kind": kind, "item": item}
    raise CombatSessionError("unsupported supply command")


def _fight_source(source: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    campaign = source["campaign"]
    entry = copy.deepcopy(campaign["encounters"][state["encounter_index"]])
    hero = next(a for a in entry["scenario"]["actors"] if a["id"] == campaign["hero_id"])
    hero["max_hp"] = state["hp"]
    if state["ward_active"]:
        hero["defense"] += WARD_DEFENSE
    return {
        "schema_version": campaign["schema_version"],
        "campaign_id": campaign["campaign_id"],
        "world_id": campaign["world_id"],
        "hero_id": campaign["hero_id"],
        "hero_team": campaign["hero_team"],
        "encounters": [entry],
    }


def _advance(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    command = _command(raw)
    source, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active":
        raise CombatSessionError("supply campaign already terminal")
    if len(old["journal"]) >= MAX_COMMANDS:
        raise CombatSessionError("supply command budget exceeded")
    state = copy.deepcopy(old)
    kind = command["kind"]
    if kind == "buy":
        item = command["item"]
        cost = source["prices"][item]
        if state["currency"] < cost:
            raise CombatSessionError("insufficient earned currency")
        if state["inventory"][item] >= MAX_INVENTORY:
            raise CombatSessionError("supply inventory full")
        state["currency"] -= cost
        state["inventory"][item] += 1
    elif kind == "use":
        item = command["item"]
        if state["inventory"][item] <= 0:
            raise CombatSessionError("supply item not owned")
        if item == "medkit":
            maximum = _hero_max(source)
            if state["hp"] >= maximum:
                raise CombatSessionError("medkit would not restore health")
            state["hp"] = min(maximum, state["hp"] + 4)
        else:
            if state["ward_active"]:
                raise CombatSessionError("ward already prepared")
            state["ward_active"] = True
        state["inventory"][item] -= 1
    else:
        index = state["encounter_index"]
        encounter_id = source["campaign"]["encounters"][index]["scenario"]["encounter_id"]
        played = finish_campaign(_fight_source(source, state))
        result = played["state"]
        state["battles"].append({
            "encounter_id": encounter_id, "combat": played,
            "ward_used": state["ward_active"],
        })
        state["hp"] = result["hero_hp"]
        state["currency"] += result["currency"]
        if state["currency"] > MAX_CURRENCY:
            raise CombatSessionError("earned currency overflow")
        state["encounter_index"] = index + 1
        state["ward_active"] = False
        if result["phase"] != "won":
            state["phase"] = result["phase"]
        elif state["encounter_index"] == len(source["campaign"]["encounters"]):
            state["phase"] = "won"
    state["journal"].append(command)
    return _snapshot(source, state, snapshot["save"])


def verify_supply(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "save",
    }, "supply save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported supply save schema")
    _encoded(obj)
    state = obj["state"]
    journal = state.get("journal") if type(state) is dict else None
    if type(journal) is not list or len(journal) > MAX_COMMANDS:
        raise CombatSessionError("invalid supply journal")
    rebuilt = new_supply(obj["source"])
    for command in journal:
        rebuilt = _advance(rebuilt, command)
    if rebuilt != obj:
        raise CombatSessionError("supply replay, battle or save mismatch")
    return rebuilt


def advance_supply(raw: Any, command: Any) -> dict[str, Any]:
    return _advance(verify_supply(raw), command)


def finish_supply(source: Any, *, resume: Any = None) -> dict[str, Any]:
    spec = normalize_supply(source)
    snapshot = new_supply(spec) if resume is None else verify_supply(resume)
    if snapshot["source_digest"] != dig(spec):
        raise CombatSessionError("supply resume source mismatch")
    while snapshot["state"]["phase"] == "active":
        snapshot = _advance(snapshot, {"kind": "fight"})
    return verify_supply(snapshot)


def available_supply(raw: Any) -> dict[str, Any]:
    snapshot = verify_supply(raw)
    state, source = snapshot["state"], snapshot["source"]
    actions: list[dict[str, str]] = []
    if state["phase"] == "active":
        actions.append({"kind": "fight"})
        for item in ("medkit", "ward"):
            if (state["currency"] >= source["prices"][item]
                    and state["inventory"][item] < MAX_INVENTORY):
                actions.append({"kind": "buy", "item": item})
            if state["inventory"][item]:
                if item == "ward" and not state["ward_active"]:
                    actions.append({"kind": "use", "item": item})
                if item == "medkit" and state["hp"] < _hero_max(source):
                    actions.append({"kind": "use", "item": item})
    index = state["encounter_index"]
    encounters = source["campaign"]["encounters"]
    return {
        "phase": state["phase"], "hp": state["hp"],
        "currency": state["currency"], "inventory": state["inventory"],
        "ward_active": state["ward_active"],
        "next_encounter_id": encounters[index]["scenario"]["encounter_id"]
        if state["phase"] == "active" else None,
        "actions": actions,
    }


def package_supply(raw: Any) -> dict[str, Any]:
    snapshot = verify_supply(raw)
    state = snapshot["state"]
    result = {
        "schema_version": PACKAGE_SCHEMA, "claim": "offline_integrity_only",
        "snapshot": snapshot,
        "manifest": {
            "source_digest": snapshot["source_digest"],
            "state_digest": snapshot["state_digest"],
            "phase": state["phase"], "currency": state["currency"],
            "encounters_completed": len(state["battles"]),
        },
    }
    result["digest"] = dig(result)
    _encoded(result)
    return result


def verify_supply_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "claim", "snapshot", "manifest", "digest",
    }, "supply package")
    if obj["schema_version"] != PACKAGE_SCHEMA or obj["claim"] != "offline_integrity_only":
        raise CombatSessionError("unsupported supply package")
    _encoded(obj)
    if obj != package_supply(obj["snapshot"]):
        raise CombatSessionError("supply package manifest or replay mismatch")
    return obj


def original_supply() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "campaign": original_campaign(),
        "prices": {"medkit": 8, "ward": 10},
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-supply")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original earned-supply campaign")
    start = sub.add_parser("start")
    start.add_argument("--source-json", required=True)
    for name in ("verify", "available", "finish", "pack"):
        item = sub.add_parser(name)
        item.add_argument("--session-json", required=True)
    act = sub.add_parser("act")
    act.add_argument("--session-json", required=True)
    act.add_argument("--command-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = finish_supply(original_supply())
        elif args.command == "start":
            result = new_supply(_parse_json(args.source_json, "supply source"))
        elif args.command == "unpack":
            result = verify_supply_package(_parse_json(args.package_json, "supply package"))
        else:
            session = _parse_json(args.session_json, "supply save")
            if args.command == "act":
                result = advance_supply(session, _parse_json(args.command_json, "supply command"))
            elif args.command == "verify":
                result = verify_supply(session)
            elif args.command == "available":
                result = available_supply(session)
            elif args.command == "finish":
                saved = verify_supply(session)
                result = finish_supply(saved["source"], resume=saved)
            else:
                result = package_supply(session)
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError, OverflowError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
