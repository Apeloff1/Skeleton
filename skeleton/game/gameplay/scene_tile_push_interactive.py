"""Interactive JSON-line crate puzzles with verified durable checkpoints.

No implicit victory on EOF, malformed input, budget exhaustion or replay
mismatch. Invalid player turns are retried without changing saved state.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_push import (
    _json, _plate_state, _step, export_push, legal_push_actions, new_push,
    original_push, normalize_push, verify_push,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_INPUT_BYTES = 64 * 1024
MAX_RETRIES = 3


def _emit(writer: Any, event: dict[str, Any]) -> None:
    writer.write(json.dumps(
        event, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ) + "\n")
    writer.flush()


def play_push(source: Any, *, reader: Any = None, writer: Any = None,
              resume: Any = None) -> dict[str, Any]:
    """Run player turns against canonical tile collision and pressure gates.

    The input protocol is one JSON action per line. Each prompt includes the
    state digest, legal actions and activated plate set. This makes the same
    interface usable from a terminal, a web frontend or a gamepad adapter.
    """
    input_stream = sys.stdin if reader is None else reader
    output_stream = sys.stdout if writer is None else writer
    spec = normalize_push(source)
    session = new_push(spec) if resume is None else verify_push(resume)
    if session["source_digest"] != dig(spec):
        raise SceneTravelError("push interactive source/save mismatch")
    while session["state"]["phase"] == "active":
        state = session["state"]
        if state["tick"] >= spec["turn_limit"]:
            raise SceneTravelError("push interactive turn budget exhausted")
        tile = state["tile"]["state"]
        scene_id = tile["scene"]["state"]["scene_id"]
        legal = legal_push_actions(session)
        if not legal:
            raise SceneTravelError("push interactive no legal actions")
        _emit(output_stream, {
            "event": "push_turn", "tick": state["tick"],
            "scene_id": scene_id, "position": tile["position"],
            "crates": state["crates"],
            "active_plates": sorted(
                ident for ident, active in _plate_state(spec, state["crates"]).items()
                if active
            ),
            "legal_actions": legal, "state_digest": session["state_digest"],
            "remaining_turns": spec["turn_limit"] - state["tick"],
        })
        for attempt in range(MAX_RETRIES):
            line = input_stream.readline(MAX_INPUT_BYTES + 1)
            if not line:
                raise SceneTravelError("push interactive input ended before terminal")
            try:
                if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
                    raise SceneTravelError("push interactive input exceeds byte budget")
                action = _json(line)
                candidate = _step(session, action)
            except (SceneTravelError, ValueError, TypeError,
                    UnicodeError, RecursionError) as exc:
                _emit(output_stream, {
                    "event": "push_rejected", "error": str(exc),
                    "state_digest": session["state_digest"],
                    "remaining_retries": MAX_RETRIES - attempt - 1,
                })
                if attempt + 1 == MAX_RETRIES:
                    raise SceneTravelError("three invalid push actions") from exc
            else:
                session = verify_push(candidate)
                _emit(output_stream, {
                    "event": "push_accepted", "tick": session["state"]["tick"],
                    "state_digest": session["state_digest"],
                    "receipt": session["journal"][-1]["receipt"],
                })
                break
    bundle = export_push(session)
    _emit(output_stream, {
        "event": "push_terminal", "phase": session["state"]["phase"],
        "state_digest": session["state_digest"],
        "source_digest": session["source_digest"],
        "portable_checksum": bundle["checksum"], "session": session,
    })
    return session


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-push-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    live = sub.add_parser("play")
    live.add_argument("--source-json")
    live.add_argument("--session-json")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            from io import StringIO
            source, actions = original_push()
            reader = StringIO("".join(json.dumps(a) + "\n" for a in actions))
            play_push(source, reader=reader)
        else:
            saved = (_json(args.session_json)
                     if args.session_json is not None else None)
            source = (_json(args.source_json)
                      if args.source_json is not None else
                      saved["source"] if saved is not None else original_push()[0])
            play_push(source, resume=saved)
        return 0
    except (SceneTravelError, KeyError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
