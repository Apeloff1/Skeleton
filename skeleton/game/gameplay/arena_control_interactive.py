"""JSON-line playable control-point arena with bounded input and safe recovery.

Player-team actions are never supplied for opponents. Opponent decisions use
the canonical deterministic tactical policy. EOF, malformed commands and
input exhaustion return the last replay-verifiable checkpoint, not an
unverified success or a mutated partial action.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from skeleton.game.gameplay.arena_control import (
    _advance_control, _encoded, new_control, normalize_control,
    original_control, verify_control,
)
from skeleton.game.gameplay.arena_control_solver import _choices
from skeleton.game.gameplay.arena_control_render import render_control
from skeleton.game.gameplay.arena_policy import _decide
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.tactical_arena import _active
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _parse_json,
)

SCHEMA = "skeleton.arena_control_interactive.v1"
MAX_INPUT_BYTES = 8192
MAX_INPUTS = 64


def _message(stream: TextIO, value: dict[str, Any]) -> None:
    stream.write(_encoded(value) + "\n")
    stream.flush()


def _actor(session: dict[str, Any]) -> tuple[str, str]:
    arena = session["arena_session"]
    actor_id, _ = _active(arena["source"], arena["state"])
    teams = {actor["id"]: actor["team"] for actor in arena["source"]["actors"]}
    return actor_id, teams[actor_id]


def _snapshot(session: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "type": "checkpoint",
        "status": status, "reason": reason,
        "source_digest": session["source_digest"],
        "session": session, "session_digest": dig(session),
    }


def play_interactive(source: Any, team: Any, *, resume: Any = None,
                     input_stream: TextIO | None = None,
                     output_stream: TextIO | None = None,
                     max_inputs: int = MAX_INPUTS) -> dict[str, Any]:
    spec = normalize_control(source)
    selected = _id(team, "team")
    teams = {actor["team"] for actor in spec["arena"]["actors"]}
    if selected not in teams:
        raise CombatSessionError("unknown interactive player team")
    budget = _integer(max_inputs, "max_inputs", 1, MAX_INPUTS)
    session = new_control(spec) if resume is None else verify_control(resume)
    if session["source_digest"] != dig(spec):
        raise CombatSessionError("interactive control-point source mismatch")
    reader = input_stream if input_stream is not None else sys.stdin
    writer = output_stream if output_stream is not None else sys.stdout
    inputs = 0
    while session["state"]["phase"] == "active":
        actor_id, actor_team = _actor(session)
        if actor_team != selected:
            action = _decide(session["arena_session"])
            session = _advance_control(session, action)
            _message(writer, {
                "schema_version": SCHEMA, "type": "opponent_action",
                "action": action, "tick": session["state"]["tick"],
                "state_digest": session["state_digest"],
                "scores": session["state"]["scores"],
            })
            continue
        if inputs >= budget:
            result = _snapshot(session, "checkpoint", "input_budget_exhausted")
            _message(writer, result)
            return result
        _message(writer, {
            "schema_version": SCHEMA, "type": "player_turn",
            "actor_id": actor_id, "team": selected,
            "tick": session["state"]["tick"],
            "scores": session["state"]["scores"],
            "legal_actions": _choices(session),
            "board": render_control(session),
            "state_digest": session["state_digest"],
        })
        line = reader.readline(MAX_INPUT_BYTES + 1)
        if not line:
            result = _snapshot(session, "checkpoint", "input_eof")
            _message(writer, result)
            return result
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            result = _snapshot(session, "rejected", "input_too_large")
            _message(writer, result)
            return result
        inputs += 1
        try:
            action = _parse_json(line, "player control-point action")
            # No player may move an opponent even if the action is otherwise legal.
            if type(action) is not dict or action.get("actor_id") != actor_id:
                raise CombatSessionError("player does not own active actor")
            advanced = _advance_control(session, action)
        except (CombatSessionError, KeyError, TypeError, ValueError) as exc:
            result = _snapshot(session, "rejected", str(exc))
            _message(writer, result)
            return result
        session = advanced
        _message(writer, {
            "schema_version": SCHEMA, "type": "player_action",
            "action": session["journal"][-1]["action"],
            "tick": session["state"]["tick"],
            "scores": session["state"]["scores"],
            "state_digest": session["state_digest"],
            "event_receipt": session["journal"][-1]["receipt"],
        })
    result = _snapshot(session, "completed", session["state"]["phase"])
    _message(writer, result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-interactive")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Play original canal beacon capture interactively")
    demo.add_argument("--team", default="wayfarers")
    play = sub.add_parser("play")
    play.add_argument("--source-json", required=True)
    play.add_argument("--team", required=True)
    play.add_argument("--resume-json")
    play.add_argument("--max-inputs", type=int, default=MAX_INPUTS)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = play_interactive(original_control(), args.team)
        else:
            source = _parse_json(args.source_json, "control-point source")
            result = play_interactive(
                source, args.team,
                resume=_parse_json(args.resume_json, "control-point checkpoint")
                if args.resume_json is not None else None,
                max_inputs=args.max_inputs,
            )
        return 2 if result["status"] == "rejected" else 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
