"""Bounded interactive merchant-hour gameplay with restartable verified saves."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_hours import (
    _advance, export_hours, merchant_board, new_hours, original_hours,
    verify_hours,
)
from skeleton.game.gameplay.scene_market_interactive import (
    MAX_RETRIES, _emit, parse_market_command,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_BYTES
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session, "portable": export_hours(session),
    })


def play_hours(source: Any = None, *, session: Any = None,
               expected_source_digest: str | None = None,
               checkpoint_every: int = 8,
               input_stream: Any = None,
               output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one merchant source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("invalid merchant checkpoint interval")
    current = new_hours(source) if session is None else verify_hours(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or current["source_digest"] != expected_source_digest):
            raise SceneTravelError("merchant source digest not trusted")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        _emit(writer, {"event": "merchant_board", "board": merchant_board(current)})
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("merchant input ended; checkpoint emitted")
            try:
                action = parse_market_command(line)
                updated = _advance(current, action)
            except (SceneTravelError, ValueError, TypeError, KeyError) as exc:
                _emit(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": MAX_RETRIES - attempt - 1,
                })
                if attempt == MAX_RETRIES - 1:
                    _checkpoint(writer, current, "invalid_commands")
                    raise SceneTravelError(
                        "three invalid merchant commands; checkpoint emitted"
                    ) from exc
            else:
                current = updated
                _emit(writer, {
                    "event": "accepted", "action": action,
                    "tick": current["state"]["tick"],
                    "state_digest": current["state_digest"],
                })
                break
        if (current["state"]["phase"] == "active"
                and current["state"]["tick"] % checkpoint_every == 0):
            _checkpoint(writer, current, "interval")
    _checkpoint(writer, current, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": current["state"]["phase"],
        "state_digest": current["state_digest"],
        "credits": current["state"]["market"]["state"]["credits"],
        "purchases_by_merchant": current["state"]["purchases_by_merchant"],
    })
    return current


def _commands(actions: list[dict[str, Any]]) -> str:
    commands = []
    for action in actions:
        if action["kind"] == "tile":
            nested = action["action"]
            field = ("direction" if nested["kind"] == "move"
                     else "pickup_id" if nested["kind"] == "collect" else "exit_id")
            commands.append(nested["kind"] + " " + nested[field])
        else:
            field = {"buy": "offer_id", "craft": "recipe_id",
                     "deliver": "delivery_id"}[action["kind"]]
            commands.append(action["kind"] + " " + action[field])
    return "\n".join(commands) + "\n"


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-hours-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    play = sub.add_parser("play")
    group = play.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    play.add_argument("--source-digest")
    play.add_argument("--checkpoint-every", type=int, default=8)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_hours()
            play_hours(source, input_stream=io.StringIO(_commands(actions)))
        else:
            play_hours(
                _json(args.source_json) if args.source_json is not None else None,
                session=_json(args.session_json)
                if args.session_json is not None else None,
                expected_source_digest=args.source_digest,
                checkpoint_every=args.checkpoint_every,
            )
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
