"""Original offline combat drills: playable lessons, deterministic opponents and replay.

A drill never executes authored code. Canonical combat owns all state transitions;
every exported session is reconstructed from source and the player's commands.
Checksums establish consistency, not provenance or authorization.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.tactical_policy import _decide_verified, POLICY_VERSION
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _active_actor, _advance,
    _id, _integer, _object, _parse_json, new_session, normalize_scenario,
    original_demo, verify_session,
)

SCHEMA = "skeleton.combat_drill.v1"
MAX_PLAYER_ACTIONS = 64


def normalize_drill(raw: Any) -> dict[str, Any]:
    """Fail closed on unknown fields, unsupported source and impossible goals."""
    obj = _object(raw, {
        "schema_version", "drill_id", "scenario", "player_team",
        "max_player_actions", "minimum_survivor_hp",
    }, "drill")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported drill schema")
    spec = normalize_scenario(obj["scenario"])
    team = _id(obj["player_team"], "player_team")
    if team not in {actor["team"] for actor in spec["actors"]}:
        raise CombatSessionError("player team absent from scenario")
    limit = _integer(
        obj["max_player_actions"], "max_player_actions", 1, MAX_PLAYER_ACTIONS,
    )
    if limit > spec["turn_limit"]:
        raise CombatSessionError("player action budget exceeds turn limit")
    hp = _integer(obj["minimum_survivor_hp"], "minimum_survivor_hp", 1, 10000)
    max_hp = max(
        actor["max_hp"] for actor in spec["actors"] if actor["team"] == team
    )
    if hp > max_hp:
        raise CombatSessionError("minimum survivor HP is impossible")
    return {
        "schema_version": SCHEMA,
        "drill_id": _id(obj["drill_id"], "drill_id"),
        "scenario": spec, "player_team": team,
        "max_player_actions": limit, "minimum_survivor_hp": hp,
    }


def _actor_team(spec: dict[str, Any], actor_id: str) -> str:
    for actor in spec["actors"]:
        if actor["id"] == actor_id:
            return actor["team"]
    raise CombatSessionError("unknown active actor")


def _bots(combat: dict[str, Any], player_team: str) -> dict[str, Any]:
    """Advance only enemy turns, bounded by canonical combat turn budget."""
    while combat["state"]["phase"] == "active":
        actor_id, _ = _active_actor(combat["scenario"], combat["state"])
        if _actor_team(combat["scenario"], actor_id) == player_team:
            break
        combat = _advance(combat, _decide_verified(combat))
    return combat


def _outcome(source: dict[str, Any], combat: dict[str, Any],
             player_actions: list[dict[str, str]]) -> str:
    state = combat["state"]
    if state["phase"] == "won":
        if state["winner"] != source["player_team"]:
            return "failed"
        survivors = [
            state["actors"][actor["id"]]["hp"]
            for actor in source["scenario"]["actors"]
            if actor["team"] == source["player_team"]
        ]
        return (
            "passed" if max(survivors) >= source["minimum_survivor_hp"]
            else "failed"
        )
    if state["phase"] == "draw" or len(player_actions) >= source["max_player_actions"]:
        return "failed"
    return "active"


def _snapshot(source: dict[str, Any], combat: dict[str, Any],
              actions: list[dict[str, str]]) -> dict[str, Any]:
    outcome = _outcome(source, combat, actions)
    record = {
        "schema_version": SCHEMA,
        "source": source,
        "source_digest": dig(source),
        "policy_version": POLICY_VERSION,
        "combat": combat,
        "player_actions": actions,
        "outcome": outcome,
    }
    return {**record, "receipt": dig(record)}


def new_drill(raw: Any) -> dict[str, Any]:
    """Compile an authored drill into a playable, immutable opening checkpoint."""
    source = normalize_drill(raw)
    combat = _bots(new_session(source["scenario"]), source["player_team"])
    return _snapshot(source, combat, [])


def _step_unchecked(session: dict[str, Any], action: Any) -> dict[str, Any]:
    if session["outcome"] != "active":
        raise CombatSessionError("drill already terminal or action budget exhausted")
    combat = session["combat"]
    actor_id, _ = _active_actor(combat["scenario"], combat["state"])
    if _actor_team(combat["scenario"], actor_id) != session["source"]["player_team"]:
        raise CombatSessionError("expected player-controlled turn")
    if type(action) is not dict:
        raise CombatSessionError("invalid player action")
    combat = _advance(combat, action)
    combat = _bots(combat, session["source"]["player_team"])
    canonical_action = combat["journal"][
        len(session["combat"]["journal"])
    ]["action"]
    actions = [*session["player_actions"], canonical_action]
    return _snapshot(session["source"], combat, actions)


def verify_drill(raw: Any) -> dict[str, Any]:
    """Replay every human command and every policy action from canonical source."""
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "policy_version",
        "combat", "player_actions", "outcome", "receipt",
    }, "drill session")
    if obj["schema_version"] != SCHEMA or obj["policy_version"] != POLICY_VERSION:
        raise CombatSessionError("unsupported drill session/policy")
    actions = obj["player_actions"]
    if type(actions) is not list or len(actions) > MAX_PLAYER_ACTIONS:
        raise CombatSessionError("invalid drill action journal")
    rebuilt = new_drill(obj["source"])
    for action in actions:
        rebuilt = _step_unchecked(rebuilt, action)
    if rebuilt != obj:
        raise CombatSessionError("drill replay, grade or receipt mismatch")
    verify_session(rebuilt["combat"])
    return rebuilt


def advance_drill(payload: Any, action: Any) -> dict[str, Any]:
    return _step_unchecked(verify_drill(payload), action)


def simulate_drill(source: Any, actions: Any) -> dict[str, Any]:
    if type(actions) is not list or len(actions) > MAX_PLAYER_ACTIONS:
        raise CombatSessionError("invalid drill action batch")
    session = new_drill(source)
    for action in actions:
        session = _step_unchecked(session, action)
    return session


def preview_drill(source: Any) -> dict[str, Any]:
    """Return legal initial actor, available targets and authored success limits."""
    session = new_drill(source)
    combat = session["combat"]
    state = combat["state"]
    actor_id, _ = _active_actor(combat["scenario"], state)
    team = session["source"]["player_team"]
    targets = sorted(
        actor["id"] for actor in combat["scenario"]["actors"]
        if actor["team"] != team and state["actors"][actor["id"]]["hp"] > 0
    )
    return {
        "schema_version": SCHEMA,
        "drill_id": session["source"]["drill_id"],
        "source_digest": session["source_digest"],
        "opening_state_digest": combat["state_digest"],
        "first_player_actor": actor_id,
        "legal_targets": targets,
        "player_action_budget": session["source"]["max_player_actions"],
        "minimum_survivor_hp": session["source"]["minimum_survivor_hp"],
        "opening_enemy_turns": len(combat["journal"]),
    }


def original_drill() -> dict[str, Any]:
    scenario, _ = original_demo()
    return {
        "schema_version": SCHEMA,
        "drill_id": "glass_moor_bridge_watch",
        "scenario": scenario,
        "player_team": "wayfarers",
        "max_player_actions": 4,
        "minimum_survivor_hp": 2,
    }


def play_drill(source: Any, *, reader: Any = None, writer: Any = None,
               resume: Any = None) -> dict[str, Any]:
    """Interactive JSON-line play with bounded retries and no implicit auto-win."""
    input_stream = sys.stdin if reader is None else reader
    output_stream = sys.stdout if writer is None else writer
    session = new_drill(source) if resume is None else verify_drill(resume)
    if session["source_digest"] != dig(normalize_drill(source)):
        raise CombatSessionError("resumed drill source mismatch")
    while session["outcome"] == "active":
        combat = session["combat"]
        actor_id, _ = _active_actor(combat["scenario"], combat["state"])
        output_stream.write(json.dumps({
            "event": "drill_turn", "actor_id": actor_id,
            "tick": combat["state"]["tick"],
            "state_digest": combat["state_digest"],
            "remaining_player_actions": (
                session["source"]["max_player_actions"] - len(session["player_actions"])
            ),
            "targets": [
                actor["id"] for actor in combat["scenario"]["actors"]
                if actor["team"] != session["source"]["player_team"]
                and combat["state"]["actors"][actor["id"]]["hp"] > 0
            ],
            "actions": ["attack", "guard", "rest"],
        }, sort_keys=True) + "\n")
        output_stream.flush()
        for attempt in range(3):
            line = input_stream.readline(MAX_CLI_BYTES + 1)
            if not line:
                raise CombatSessionError("drill input ended before terminal grade")
            try:
                if len(line.encode("utf-8")) > MAX_CLI_BYTES:
                    raise CombatSessionError("drill input exceeds size budget")
                candidate = _parse_json(line, "player action")
                updated = _step_unchecked(session, candidate)
            except CombatSessionError as exc:
                output_stream.write(json.dumps({
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": 2 - attempt,
                }, sort_keys=True) + "\n")
                output_stream.flush()
                if attempt == 2:
                    raise CombatSessionError("three invalid drill actions") from exc
            else:
                session = updated
                break
    output_stream.write(json.dumps({
        "event": "drill_terminal", "session": session,
    }, sort_keys=True, separators=(",", ":")) + "\n")
    output_stream.flush()
    return session


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-drill")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play an original replay-verified lesson automatically")
    preview = sub.add_parser("preview")
    preview.add_argument("--source-json")
    play = sub.add_parser("play")
    play.add_argument("--source-json")
    play.add_argument("--session-json")
    run = sub.add_parser("simulate")
    run.add_argument("--source-json", required=True)
    run.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("--session-json", required=True)
    advance.add_argument("--action-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = simulate_drill(original_drill(), [
                {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
                {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
            ])
        elif args.command == "preview":
            result = preview_drill(
                _parse_json(args.source_json, "drill source")
                if args.source_json else original_drill()
            )
        elif args.command == "play":
            if args.source_json and args.session_json:
                raise CombatSessionError("provide source or session, not both")
            saved = _parse_json(args.session_json, "drill session") if args.session_json else None
            source = saved["source"] if saved is not None else (
                _parse_json(args.source_json, "drill source")
                if args.source_json else original_drill()
            )
            play_drill(source, resume=saved)
            return 0
        elif args.command == "simulate":
            result = simulate_drill(
                _parse_json(args.source_json, "drill source"),
                _parse_json(args.actions_json, "player actions"),
            )
        elif args.command == "verify":
            result = verify_drill(_parse_json(args.session_json, "drill session"))
        else:
            result = advance_drill(
                _parse_json(args.session_json, "drill session"),
                _parse_json(args.action_json, "player action"),
            )
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("drill output exceeds 128 KiB")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
