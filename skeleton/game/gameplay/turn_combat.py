"""Deterministic, source-bound, offline turn combat for authored game encounters.

This is a pure game simulation: it never executes scripts, calls a provider,
opens a network connection, or grants authority to the combat event journal.
Receipts are integrity checks, not signatures or proof of trusted authorship.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus,
    GameplayEvent,
    SaveableGameplayState,
    dig,
)

SCHEMA = "skeleton.turn_combat.v1"
MAX_ACTORS = 16
MAX_TURNS = 512
MAX_CLI_BYTES = 131072
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}\Z")


class CombatSessionError(ValueError):
    """Invalid authored encounter, command, save, or replay receipt."""


def _id(value: Any, name: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise CombatSessionError(f"invalid {name}")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CombatSessionError(f"invalid {name}")
    return value


def _object(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise CombatSessionError(f"invalid {name} fields")
    return value


def normalize_scenario(raw: Any) -> dict[str, Any]:
    """Validate the complete author-controlled input before any simulation."""
    obj = _object(
        raw, {"schema_version", "world_id", "encounter_id", "actors", "turn_limit"},
        "scenario",
    )
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported combat schema")
    world = _id(obj["world_id"], "world_id")
    encounter = _id(obj["encounter_id"], "encounter_id")
    limit = _integer(obj["turn_limit"], "turn_limit", 1, MAX_TURNS)
    actors = obj["actors"]
    if type(actors) is not list or not 2 <= len(actors) <= MAX_ACTORS:
        raise CombatSessionError("actor count outside 2..16")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    teams: set[str] = set()
    for entry in actors:
        actor = _object(
            entry, {"id", "team", "max_hp", "attack", "defense", "speed"}, "actor"
        )
        actor_id = _id(actor["id"], "actor_id")
        team = _id(actor["team"], "team")
        if actor_id in seen:
            raise CombatSessionError("duplicate actor_id")
        seen.add(actor_id)
        teams.add(team)
        normalized.append({
            "id": actor_id,
            "team": team,
            "max_hp": _integer(actor["max_hp"], "max_hp", 1, 10000),
            "attack": _integer(actor["attack"], "attack", 1, 1000),
            "defense": _integer(actor["defense"], "defense", 0, 1000),
            "speed": _integer(actor["speed"], "speed", 0, 1000),
        })
    if len(teams) < 2:
        raise CombatSessionError("encounter needs at least two opposing teams")
    normalized.sort(key=lambda actor: actor["id"])
    return {
        "schema_version": SCHEMA, "world_id": world, "encounter_id": encounter,
        "actors": normalized, "turn_limit": limit,
    }


def _event_bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "combat.action", event["action"]["actor_id"], event["receipt"])
        for i, event in enumerate(journal)
    )).digest


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["world_id"],
        schema_version=1,
        tick=state["tick"],
        state_digest=dig(state),
        canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_session(scenario: Any) -> dict[str, Any]:
    """Create a canonical snapshot with stable turn ordering and source identity."""
    spec = normalize_scenario(scenario)
    actors = {
        actor["id"]: {"hp": actor["max_hp"], "guard": False}
        for actor in spec["actors"]
    }
    state = {
        "tick": 0, "phase": "active", "winner": None,
        "next_index": 0, "actors": actors,
    }
    return {
        "schema_version": SCHEMA, "scenario": spec,
        "source_digest": dig(spec), "state": state, "state_digest": dig(state),
        "journal": [], "event_bus_digest": EventBus().digest,
        "save": _save(spec, state),
    }


def _turn_order(spec: dict[str, Any]) -> list[str]:
    return [
        actor["id"] for actor in sorted(
            spec["actors"], key=lambda actor: (-actor["speed"], actor["id"])
        )
    ]


def _active_actor(spec: dict[str, Any], state: dict[str, Any]) -> tuple[str, int]:
    order = _turn_order(spec)
    for offset in range(len(order)):
        index = (state["next_index"] + offset) % len(order)
        actor_id = order[index]
        if state["actors"][actor_id]["hp"] > 0:
            return actor_id, index
    raise CombatSessionError("no active actor")


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is not dict or raw.get("kind") not in ("attack", "guard", "rest"):
        raise CombatSessionError("unsupported combat action")
    kind = raw["kind"]
    required = {"kind", "actor_id", "target_id"} if kind == "attack" else {"kind", "actor_id"}
    _object(raw, required, "action")
    result = {"kind": kind, "actor_id": _id(raw["actor_id"], "actor_id")}
    if kind == "attack":
        result["target_id"] = _id(raw["target_id"], "target_id")
    return result


def _advance(session: dict[str, Any], raw_action: Any) -> dict[str, Any]:
    """Apply one validated command; the caller retains the prior immutable snapshot."""
    spec = session["scenario"]
    old = session["state"]
    if old["phase"] != "active":
        raise CombatSessionError("combat already terminal")
    action = _action(raw_action)
    actor_id, index = _active_actor(spec, old)
    if action["actor_id"] != actor_id:
        raise CombatSessionError("out-of-turn actor")
    stats = {actor["id"]: actor for actor in spec["actors"]}
    state = {
        "tick": old["tick"] + 1, "phase": "active", "winner": None,
        "next_index": (index + 1) % len(stats),
        "actors": {key: dict(value) for key, value in old["actors"].items()},
    }
    if action["kind"] == "attack":
        target = action["target_id"]
        if target not in stats or state["actors"][target]["hp"] == 0:
            raise CombatSessionError("target missing or defeated")
        if stats[target]["team"] == stats[actor_id]["team"]:
            raise CombatSessionError("friendly fire denied")
        damage = max(1, stats[actor_id]["attack"] - stats[target]["defense"])
        if state["actors"][target]["guard"]:
            damage = max(1, damage // 2)
            state["actors"][target]["guard"] = False
        state["actors"][target]["hp"] = max(0, state["actors"][target]["hp"] - damage)
    elif action["kind"] == "guard":
        state["actors"][actor_id]["guard"] = True
    else:
        state["actors"][actor_id]["hp"] = min(
            stats[actor_id]["max_hp"], state["actors"][actor_id]["hp"] + 2
        )
    alive = {
        stats[actor_id]["team"]
        for actor_id, status in state["actors"].items() if status["hp"] > 0
    }
    if len(alive) == 1:
        state["phase"] = "won"
        state["winner"] = next(iter(alive))
    elif state["tick"] >= spec["turn_limit"]:
        state["phase"] = "draw"
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    return {
        "schema_version": SCHEMA, "scenario": spec,
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": journal, "event_bus_digest": _event_bus(journal),
        "save": _save(spec, state, session["save"]),
    }


def verify_session(payload: Any) -> dict[str, Any]:
    """Recompute every turn and save lineage, rejecting drift or forged ordering.

    SHA-256 is not an authenticity signature. An attacker who controls both
    the authored source and receipts can rewrite them; external trust requires
    the application's separately governed provenance/authorization layer.
    """
    obj = _object(payload, {
        "schema_version", "scenario", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported session schema")
    rebuilt = new_session(obj["scenario"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > rebuilt["scenario"]["turn_limit"]:
        raise CombatSessionError("invalid journal budget")
    for recorded in journal:
        if type(recorded) is not dict:
            raise CombatSessionError("invalid journal entry")
        try:
            rebuilt = _advance(rebuilt, recorded["action"])
        except (KeyError, TypeError) as exc:
            raise CombatSessionError("malformed journal action") from exc
        if rebuilt["journal"][-1] != recorded:
            raise CombatSessionError("journal replay mismatch")
    if rebuilt != obj:
        raise CombatSessionError("session snapshot or save lineage mismatch")
    return rebuilt


def resume_session(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_session(payload)
    if type(actions) is not list or len(actions) > MAX_TURNS:
        raise CombatSessionError("invalid action batch")
    if len(session["journal"]) + len(actions) > session["scenario"]["turn_limit"]:
        raise CombatSessionError("action batch exceeds turn limit")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate(scenario: Any, actions: Any) -> dict[str, Any]:
    return resume_session(new_session(scenario), actions)


def original_demo() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Original two-team encounter, not copied or derived from another game."""
    spec = {
        "schema_version": SCHEMA, "world_id": "glass_moor",
        "encounter_id": "bridge_watch", "turn_limit": 16,
        "actors": [
            {"id": "scout", "team": "wayfarers", "max_hp": 12, "attack": 5, "defense": 2, "speed": 3},
            {"id": "warden", "team": "reedbound", "max_hp": 7, "attack": 3, "defense": 1, "speed": 2},
        ],
    }
    actions = [
        {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
        {"kind": "attack", "actor_id": "warden", "target_id": "scout"},
        {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
    ]
    return spec, actions



def play_interactive(scenario: Any, *, input_stream: Any = None,
                     output_stream: Any = None) -> dict[str, Any]:
    """Play a live offline encounter using bounded, accessible JSON-line turns.

    Each prompt carries the current actor and state hash. Invalid input can
    be retried up to three times per turn without mutating the saved state.
    EOF is an explicit failure, never an implicit victory or fabricated save.
    """
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    session = new_session(scenario)
    while session["state"]["phase"] == "active":
        actor_id, _ = _active_actor(session["scenario"], session["state"])
        opponents = sorted(
            actor["id"] for actor in session["scenario"]["actors"]
            if actor["team"] != next(
                item["team"] for item in session["scenario"]["actors"]
                if item["id"] == actor_id
            ) and session["state"]["actors"][actor["id"]]["hp"] > 0
        )
        writer.write(json.dumps({
            "event": "turn", "actor_id": actor_id, "tick": session["state"]["tick"],
            "state_digest": session["state_digest"], "targets": opponents,
            "actions": ["attack", "guard", "rest"],
            "hp": {key: value["hp"] for key, value in session["state"]["actors"].items()},
        }, sort_keys=True) + "\n")
        writer.flush()
        for attempt in range(3):
            line = reader.readline(MAX_CLI_BYTES + 1)
            if not line:
                raise CombatSessionError("input ended before terminal combat")
            if len(line.encode("utf-8")) > MAX_CLI_BYTES:
                raise CombatSessionError("interactive action exceeds 128 KiB")
            try:
                action = _parse_json(line, "action")
                next_session = _advance(session, action)
            except CombatSessionError as exc:
                writer.write(json.dumps({
                    "event": "rejected", "error": str(exc), "remaining_retries": 2 - attempt,
                }, sort_keys=True) + "\n")
                writer.flush()
                if attempt == 2:
                    raise CombatSessionError("three invalid actions in one turn") from exc
            else:
                session = next_session
                break
    writer.write(json.dumps({
        "event": "terminal", "session": session,
    }, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()
    return session


def _parse_json(raw: str, label: str) -> Any:
    if len(raw.encode("utf-8")) > MAX_CLI_BYTES:
        raise CombatSessionError(f"{label} exceeds 128 KiB")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CombatSessionError(f"invalid {label} JSON") from exc


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run a complete original offline encounter")
    live = sub.add_parser("play", help="Interactively play an offline encounter")
    live.add_argument("--scenario-json")
    live.add_argument("--demo", action="store_true")
    start = sub.add_parser("simulate", help="Compile source and apply ordered actions")
    start.add_argument("--scenario-json", required=True)
    start.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify", help="Replay and verify an exported save")
    verify.add_argument("--session-json", required=True)
    resume = sub.add_parser("resume", help="Resume an integrity-checked save")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "play":
            if bool(args.demo) == bool(args.scenario_json):
                raise CombatSessionError("play needs exactly one of --demo or --scenario-json")
            scenario = original_demo()[0] if args.demo else _parse_json(args.scenario_json, "scenario")
            play_interactive(scenario)
            return 0
        if args.command == "demo":
            spec, actions = original_demo()
            result = simulate(spec, actions)
        elif args.command == "simulate":
            result = simulate(
                _parse_json(args.scenario_json, "scenario"),
                _parse_json(args.actions_json, "actions"),
            )
        elif args.command == "verify":
            result = verify_session(_parse_json(args.session_json, "session"))
        else:
            result = resume_session(
                _parse_json(args.session_json, "session"),
                _parse_json(args.actions_json, "actions"),
            )
        print(json.dumps(result, sort_keys=True, separators=(",",":"), ensure_ascii=False))
        return 0
    except CombatSessionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
