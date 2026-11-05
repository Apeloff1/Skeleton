"""JSON-line interactive market contracts with durable canonical checkpoints.

Only the canonical contract/market reducers advance state. Rejected input
never mutates the previous save, and EOF emits a verified resumable checkpoint.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_contract import (
    _advance, contract_board, new_contract, original_contract, verify_contract,
)
from skeleton.game.gameplay.scene_market_interactive import parse_market_command
from skeleton.game.gameplay.scene_tile_walk import MAX_BYTES
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_RETRIES = 3


def _emit(writer: Any, value: dict[str, Any]) -> None:
    writer.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    })


def play_contract(source: Any = None, *, session: Any = None,
                  expected_source_digest: str | None = None,
                  checkpoint_every: int = 8,
                  input_stream: Any = None,
                  output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one contract source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("invalid contract checkpoint interval")
    current = new_contract(source) if session is None else verify_contract(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or expected_source_digest != current["source_digest"]):
            raise SceneTravelError("contract source digest does not match trusted input")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        _emit(writer, {"event": "board", "board": contract_board(current)})
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("contract input ended; verified checkpoint emitted")
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
                        "three invalid contract commands; checkpoint emitted"
                    ) from exc
            else:
                current = updated
                _emit(writer, {
                    "event": "accepted", "action": current["journal"][-1]["action"],
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
        "score": current["state"]["score"],
        "completed": current["state"]["completed"],
        "state_digest": current["state_digest"],
    })
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-contract-play")
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
            source, actions = original_contract()
            commands = "\n".join(json.dumps(action) for action in actions) + "\n"
            play_contract(source, input_stream=io.StringIO(commands),
                          checkpoint_every=4)
        else:
            play_contract(
                _json(args.source_json) if args.source_json is not None else None,
                session=(_json(args.session_json)
                         if args.session_json is not None else None),
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
