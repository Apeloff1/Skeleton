"""Replay-verifiable offline combat campaign with durable inter-encounter state.

The canonical combat engine owns every turn. This orchestrator binds authored
encounters, bounded hero health and earned currency to a single source digest.
It never grants rewards from an unverified client-supplied combat snapshot.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.tactical_policy import run_autoplay
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object,
    _parse_json, normalize_scenario,
)

SCHEMA = "skeleton.combat_campaign.v1"
MAX_ENCOUNTERS = 4
MAX_ENCOUNTER_TURNS = 32
MAX_CURRENCY = 1000000


def normalize_campaign(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "campaign_id", "world_id",
                        "hero_id", "hero_team", "encounters"}, "campaign")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign schema")
    campaign_id = _id(obj["campaign_id"], "campaign_id")
    world_id = _id(obj["world_id"], "world_id")
    hero_id = _id(obj["hero_id"], "hero_id")
    hero_team = _id(obj["hero_team"], "hero_team")
    entries = obj["encounters"]
    if type(entries) is not list or not 1 <= len(entries) <= MAX_ENCOUNTERS:
        raise CombatSessionError("invalid campaign encounter count")
    encounters: list[dict[str, Any]] = []
    seen: set[str] = set()
    hero_baseline: dict[str, Any] | None = None
    for raw_entry in entries:
        entry = _object(raw_entry, {"scenario", "reward"}, "encounter")
        scenario = normalize_scenario(entry["scenario"])
        if scenario["world_id"] != world_id:
            raise CombatSessionError("campaign world identity mismatch")
        if scenario["turn_limit"] > MAX_ENCOUNTER_TURNS:
            raise CombatSessionError("campaign encounter turn budget exceeded")
        encounter_id = scenario["encounter_id"]
        if encounter_id in seen:
            raise CombatSessionError("duplicate campaign encounter")
        seen.add(encounter_id)
        heroes = [a for a in scenario["actors"] if a["id"] == hero_id]
        if len(heroes) != 1 or heroes[0]["team"] != hero_team:
            raise CombatSessionError("hero identity or team mismatch")
        if sum(a["team"] == hero_team for a in scenario["actors"]) != 1:
            raise CombatSessionError("campaign requires one hero-team actor")
        if hero_baseline is None:
            hero_baseline = heroes[0]
        elif heroes[0] != hero_baseline:
            raise CombatSessionError("hero stats must be stable across encounters")
        reward = _integer(entry["reward"], "reward", 0, MAX_CURRENCY)
        encounters.append({"scenario": scenario, "reward": reward})
    if sum(e["reward"] for e in encounters) > MAX_CURRENCY:
        raise CombatSessionError("campaign reward budget exceeded")
    return {
        "schema_version": SCHEMA, "campaign_id": campaign_id,
        "world_id": world_id, "hero_id": hero_id, "hero_team": hero_team,
        "encounters": encounters,
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["world_id"], schema_version=1,
        tick=sum(e["combat"]["state"]["tick"] for e in state["encounters"]),
        state_digest=dig(state), canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_campaign(source: Any) -> dict[str, Any]:
    spec = normalize_campaign(source)
    hero = next(
        actor for actor in spec["encounters"][0]["scenario"]["actors"]
        if actor["id"] == spec["hero_id"]
    )
    state = {
        "next_index": 0, "hero_hp": hero["max_hp"],
        "currency": 0, "phase": "active", "encounters": [],
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "save": _save(spec, state),
    }


def _advance_verified(snapshot: dict[str, Any]) -> dict[str, Any]:
    spec, previous = snapshot["source"], snapshot["state"]
    if previous["phase"] != "active":
        raise CombatSessionError("campaign already terminal")
    index = previous["next_index"]
    if not 0 <= index < len(spec["encounters"]):
        raise CombatSessionError("campaign index out of bounds")
    entry = spec["encounters"][index]
    scenario = json.loads(json.dumps(entry["scenario"]))
    hero = next(a for a in scenario["actors"] if a["id"] == spec["hero_id"])
    hero["max_hp"] = previous["hero_hp"]
    combat = run_autoplay(scenario)
    hero_hp = combat["state"]["actors"][spec["hero_id"]]["hp"]
    victory = (
        combat["state"]["phase"] == "won"
        and combat["state"]["winner"] == spec["hero_team"]
    )
    reward = entry["reward"] if victory else 0
    currency = previous["currency"] + reward
    if currency > MAX_CURRENCY:
        raise CombatSessionError("campaign currency overflow")
    next_index = index + 1
    if not victory:
        phase = "lost" if hero_hp == 0 else "draw"
    elif next_index == len(spec["encounters"]):
        phase = "won"
    else:
        phase = "active"
    state = {
        "next_index": next_index, "hero_hp": hero_hp,
        "currency": currency, "phase": phase,
        "encounters": [*previous["encounters"], {
            "encounter_id": scenario["encounter_id"],
            "reward": reward, "combat": combat,
        }],
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": snapshot["source_digest"],
        "state": state, "state_digest": dig(state),
        "save": _save(spec, state, snapshot["save"]),
    }


def verify_campaign(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "save",
    }, "campaign session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign save schema")
    rebuilt = new_campaign(obj["source"])
    state = obj["state"]
    if type(state) is not dict or type(state.get("encounters")) is not list:
        raise CombatSessionError("invalid campaign journal")
    count = len(state["encounters"])
    if count > len(rebuilt["source"]["encounters"]):
        raise CombatSessionError("campaign journal exceeds source")
    for _ in range(count):
        rebuilt = _advance_verified(rebuilt)
    if rebuilt != obj:
        raise CombatSessionError("campaign replay or save lineage mismatch")
    return rebuilt


def advance_campaign(snapshot: Any) -> dict[str, Any]:
    """Complete one authored encounter from a verified durable checkpoint."""
    return _advance_verified(verify_campaign(snapshot))


def finish_campaign(source: Any, *, resume: Any = None) -> dict[str, Any]:
    session = new_campaign(source) if resume is None else verify_campaign(resume)
    if session["source_digest"] != dig(normalize_campaign(source)):
        raise CombatSessionError("campaign resume source mismatch")
    while session["state"]["phase"] == "active":
        session = _advance_verified(session)
    return verify_campaign(session)


def original_campaign() -> dict[str, Any]:
    """Original two-encounter Lantern Harbor patrol with earned currency."""
    hero = {
        "id": "scout", "team": "wayfarers", "max_hp": 12,
        "attack": 5, "defense": 2, "speed": 3,
    }
    foes = [
        ("reed_watch", "warden", 7, 3, 1, 10),
        ("tide_gate", "mireling", 8, 4, 1, 20),
    ]
    entries = []
    for encounter, foe, hp, attack, defense, reward in foes:
        entries.append({
            "reward": reward,
            "scenario": {
                "schema_version": "skeleton.turn_combat.v1",
                "world_id": "lantern_harbor",
                "encounter_id": encounter, "turn_limit": 16,
                "actors": [
                    dict(hero),
                    {"id": foe, "team": "reedbound", "max_hp": hp,
                     "attack": attack, "defense": defense, "speed": 2},
                ],
            },
        })
    return {
        "schema_version": SCHEMA, "campaign_id": "lantern_patrol",
        "world_id": "lantern_harbor", "hero_id": "scout",
        "hero_team": "wayfarers", "encounters": entries,
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Run original offline patrol")
    start = commands.add_parser("simulate")
    start.add_argument("--source-json", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    step = commands.add_parser("advance")
    step.add_argument("--session-json", required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = finish_campaign(original_campaign())
        elif args.command == "simulate":
            result = finish_campaign(_parse_json(args.source_json, "campaign"))
        elif args.command == "verify":
            result = verify_campaign(_parse_json(args.session_json, "campaign session"))
        elif args.command == "advance":
            result = advance_campaign(_parse_json(args.session_json, "campaign session"))
        else:
            saved = _parse_json(args.session_json, "campaign session")
            result = finish_campaign(saved["source"], resume=saved)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("campaign export exceeds 128 KiB")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
