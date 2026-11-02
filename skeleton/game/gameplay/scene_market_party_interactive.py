"""Interactive cooperative market with bounded retries and verified checkpoints."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    _advance, new_party, original_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_market_party_board import inspect_party
from skeleton.game.gameplay.scene_tile_walk import MAX_BYTES
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_RETRIES = 3


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _emit(writer, {"event": "checkpoint", "reason": reason,
                   "source_digest": session["source_digest"],
                   "state_digest": session["state_digest"], "session": session})


def play_party(source: Any = None, *, session: Any = None,
               expected_source_digest: str | None = None,
               checkpoint_every: int = 8,
               input_stream: Any = None,
               output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one party source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("invalid party checkpoint interval")
    current = new_party(source) if session is None else verify_party(session)
    if (expected_source_digest is not None
            and (type(expected_source_digest) is not str
                 or current["source_digest"] != expected_source_digest)):
        raise SceneTravelError("party source digest does not match trusted input")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {"event": "started", "source_digest": current["source_digest"]})
    while current["state"]["market"]["state"]["phase"] == "active":
        state = current["state"]
        actor = current["source"]["players"][state["turn_index"]]
        board = inspect_party(current)
        _emit(writer, {"event": "turn", "legal_actions": board["legal_actions"],
                       "player_id": actor["player_id"],
                       "roles": actor["roles"], "round": state["round"],
                       "credits": state["market"]["state"]["credits"],
                       "goods": state["market"]["state"]["goods"],
                       "reputation": state["market"]["state"]["reputation"],
                       "state_digest": current["state_digest"]})
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("party input ended; checkpoint emitted")
            try:
                action = _json(line)
                updated = _advance(current, {"player_id": actor["player_id"],
                                             "action": action})
            except (SceneTravelError, ValueError, TypeError, KeyError) as exc:
                _emit(writer, {"event": "rejected", "error": str(exc),
                               "remaining_retries": MAX_RETRIES - attempt - 1})
                if attempt == MAX_RETRIES - 1:
                    _checkpoint(writer, current, "invalid_commands")
                    raise SceneTravelError(
                        "three invalid party commands; checkpoint emitted") from exc
            else:
                current = updated
                _emit(writer, {"event": "accepted", "player_id": actor["player_id"],
                               "state_digest": current["state_digest"]})
                break
        if (current["state"]["market"]["state"]["phase"] == "active"
                and current["state"]["sequence"] % checkpoint_every == 0):
            _checkpoint(writer, current, "interval")
    _checkpoint(writer, current, "terminal")
    _emit(writer, {"event": "terminal",
                   "phase": current["state"]["market"]["state"]["phase"],
                   "state_digest": current["state_digest"]})
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-play")
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
            source, turns = original_party()
            result = simulate_party(source, turns)
            _emit(sys.stdout, {"event": "terminal",
                               "phase": result["state"]["market"]["state"]["phase"],
                               "session": result})
        else:
            play_party(
                _json(args.source_json) if args.source_json is not None else None,
                session=_json(args.session_json)
                if args.session_json is not None else None,
                expected_source_digest=args.source_digest,
                checkpoint_every=args.checkpoint_every)
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
