"""Interactive, source-bound offline combat campaign with player-owned turns.

Canonical turn_combat owns damage, guard, rest, victory and event receipts.
The player may command only the authored hero; all opposing actors use the
bounded deterministic tactical policy. Encounter rewards and carried health
are recomputed from verified canonical combat journals on every restore.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import (
    MAX_ENCOUNTERS, MAX_ENCOUNTER_TURNS, MAX_CURRENCY,
    normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.tactical_policy import choose_action
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _active_actor, _advance,
    _id, _object, _parse_json, new_session, verify_session,
)

SCHEMA = "skeleton.combat_campaign_interactive.v1"
PACKAGE_SCHEMA = "skeleton.combat_campaign_interactive_package.v1"
MAX_CHOICES = MAX_ENCOUNTERS * MAX_ENCOUNTER_TURNS


def _encoded(value: Any) -> str:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise CombatSessionError("invalid interactive campaign JSON") from exc
    if len(text.encode("utf-8")) > MAX_CLI_BYTES:
        raise CombatSessionError("interactive campaign exceeds 128 KiB")
    return text


def _hero_command(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid player combat command")
    kind = raw.get("kind")
    if kind == "attack":
        item = _object(raw, {"kind", "target_id"}, "player attack")
        return {"kind": "attack", "target_id": _id(item["target_id"], "target_id")}
    if kind in ("guard", "rest"):
        _object(raw, {"kind"}, "player combat action")
        return {"kind": kind}
    raise CombatSessionError("unsupported player combat command")


def _encounter(source: dict[str, Any], index: int, hp: int) -> dict[str, Any]:
    if not 0 <= index < len(source["encounters"]) or hp <= 0:
        raise CombatSessionError("invalid next campaign encounter")
    scenario = json.loads(json.dumps(source["encounters"][index]["scenario"]))
    hero = next(a for a in scenario["actors"] if a["id"] == source["hero_id"])
    hero["max_hp"] = hp
    return new_session(scenario)


def _auto_to_hero(source: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Advance deterministic opponents, settling encounters until hero's turn."""
    max_turns = MAX_ENCOUNTERS * MAX_ENCOUNTER_TURNS + MAX_ENCOUNTERS
    for _ in range(max_turns):
        combat = state["current_combat"]
        if combat is None:
            return state
        phase = combat["state"]["phase"]
        if phase != "active":
            index = state["encounter_index"]
            winner = combat["state"]["winner"]
            victory = phase == "won" and winner == source["hero_team"]
            hp = combat["state"]["actors"][source["hero_id"]]["hp"]
            reward = source["encounters"][index]["reward"] if victory else 0
            currency = state["currency"] + reward
            if currency > MAX_CURRENCY:
                raise CombatSessionError("interactive campaign currency overflow")
            state["encounters"].append({
                "encounter_id": combat["scenario"]["encounter_id"],
                "reward": reward, "combat": verify_session(combat),
            })
            state["hero_hp"] = hp
            state["currency"] = currency
            next_index = index + 1
            state["encounter_index"] = next_index
            if not victory:
                state["phase"] = "lost" if hp == 0 else "draw"
                state["current_combat"] = None
                return state
            if next_index == len(source["encounters"]):
                state["phase"] = "won"
                state["current_combat"] = None
                return state
            state["current_combat"] = _encounter(source, next_index, hp)
            continue
        actor, _ = _active_actor(combat["scenario"], combat["state"])
        if actor == source["hero_id"]:
            return state
        action = choose_action(combat)
        state["current_combat"] = _advance(combat, action)
    raise CombatSessionError("interactive campaign automatic turn budget exceeded")


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    tick = sum(item["combat"]["state"]["tick"] for item in state["encounters"])
    if state["current_combat"] is not None:
        tick += state["current_combat"]["state"]["tick"]
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1, tick=tick,
        state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _snapshot(source: dict[str, Any], state: dict[str, Any],
              parent: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA,
        "source": source, "source_digest": dig(source),
        "state": state, "state_digest": dig(state),
        "save": _save(source, state, parent),
    }
    _encoded(result)
    return result


def new_interactive(source: Any) -> dict[str, Any]:
    spec = normalize_campaign(source)
    hero = next(
        actor for actor in spec["encounters"][0]["scenario"]["actors"]
        if actor["id"] == spec["hero_id"]
    )
    state = {
        "phase": "active", "encounter_index": 0,
        "hero_hp": hero["max_hp"], "currency": 0,
        "encounters": [], "current_combat": _encounter(spec, 0, hero["max_hp"]),
        "choices": [],
    }
    return _snapshot(spec, _auto_to_hero(spec, state))


def _advance_verified(snapshot: dict[str, Any], command: Any) -> dict[str, Any]:
    source, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active" or old["current_combat"] is None:
        raise CombatSessionError("interactive campaign already terminal")
    if len(old["choices"]) >= MAX_CHOICES:
        raise CombatSessionError("interactive campaign choice budget exceeded")
    choice = _hero_command(command)
    combat = old["current_combat"]
    actor, _ = _active_actor(combat["scenario"], combat["state"])
    if actor != source["hero_id"]:
        raise CombatSessionError("player may act only on hero turn")
    action = {"kind": choice["kind"], "actor_id": source["hero_id"]}
    if choice["kind"] == "attack":
        action["target_id"] = choice["target_id"]
    next_combat = _advance(combat, action)
    state = {
        "phase": old["phase"], "encounter_index": old["encounter_index"],
        "hero_hp": old["hero_hp"], "currency": old["currency"],
        "encounters": list(old["encounters"]),
        "current_combat": next_combat,
        "choices": [*old["choices"], choice],
    }
    return _snapshot(source, _auto_to_hero(source, state), snapshot["save"])


def verify_interactive(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "save",
    }, "interactive campaign save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported interactive campaign schema")
    _encoded(obj)
    state = obj["state"]
    choices = state.get("choices") if type(state) is dict else None
    if type(choices) is not list or len(choices) > MAX_CHOICES:
        raise CombatSessionError("invalid interactive campaign choice journal")
    rebuilt = new_interactive(obj["source"])
    for choice in choices:
        rebuilt = _advance_verified(rebuilt, choice)
    if rebuilt != obj:
        raise CombatSessionError("interactive campaign replay or save mismatch")
    return rebuilt


def advance_interactive(raw: Any, command: Any) -> dict[str, Any]:
    return _advance_verified(verify_interactive(raw), command)


def resume_interactive(raw: Any, commands: Any) -> dict[str, Any]:
    session = verify_interactive(raw)
    if (type(commands) is not list
            or len(session["state"]["choices"]) + len(commands) > MAX_CHOICES):
        raise CombatSessionError("interactive campaign command batch exceeds budget")
    for command in commands:
        session = _advance_verified(session, command)
    return verify_interactive(session)


def demo_interactive() -> dict[str, Any]:
    """Original patrol played by deterministic hero policy through real turns."""
    session = new_interactive(original_campaign())
    for _ in range(MAX_CHOICES):
        if session["state"]["phase"] != "active":
            return verify_interactive(session)
        combat = session["state"]["current_combat"]
        policy = choose_action(combat)
        choice = {key: value for key, value in policy.items() if key != "actor_id"}
        session = _advance_verified(session, choice)
    if session["state"]["phase"] == "active":
        raise CombatSessionError("interactive demo exceeded choice budget")
    return verify_interactive(session)


def package_interactive(raw: Any) -> dict[str, Any]:
    verified = verify_interactive(raw)
    state = verified["state"]
    result = {
        "schema_version": PACKAGE_SCHEMA,
        "snapshot": verified,
        "manifest": {
            "world_id": verified["source"]["world_id"],
            "campaign_id": verified["source"]["campaign_id"],
            "source_digest": verified["source_digest"],
            "state_digest": verified["state_digest"],
            "save_digest": dig(verified["save"]),
            "phase": state["phase"], "encounter_index": state["encounter_index"],
            "hero_hp": state["hero_hp"], "currency": state["currency"],
            "completed_encounters": len(state["encounters"]),
            "player_choices": len(state["choices"]),
        },
        "claim": "canonical_replay_integrity_not_authorship",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_interactive_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "snapshot", "manifest", "claim", "receipt",
    }, "interactive campaign package")
    if (obj["schema_version"] != PACKAGE_SCHEMA
            or obj["claim"] != "canonical_replay_integrity_not_authorship"):
        raise CombatSessionError("unsupported interactive campaign package")
    _encoded(obj)
    expected = package_interactive(obj["snapshot"])
    if expected != obj:
        raise CombatSessionError("interactive campaign package mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton combat-campaign-play",
        description="Play hero turns in an offline canonical multi-encounter campaign",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    start = sub.add_parser("start")
    start.add_argument("--source-json", required=True)
    act = sub.add_parser("act")
    act.add_argument("--session-json", required=True)
    act.add_argument("--command-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--commands-json", required=True)
    for name in ("verify", "pack"):
        item = sub.add_parser(name)
        item.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_interactive()
        elif args.command == "start":
            result = new_interactive(_parse_json(args.source_json, "campaign source"))
        elif args.command == "unpack":
            result = verify_interactive_package(
                _parse_json(args.package_json, "campaign package"),
            )
        else:
            saved = _parse_json(args.session_json, "campaign checkpoint")
            if args.command == "act":
                result = advance_interactive(
                    saved, _parse_json(args.command_json, "player command"),
                )
            elif args.command == "resume":
                result = resume_interactive(
                    saved, _parse_json(args.commands_json, "player commands"),
                )
            elif args.command == "verify":
                result = verify_interactive(saved)
            else:
                result = package_interactive(saved)
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
