"""Interactive tile survival with bounded input and restartable checkpoints.

Only canonical legal actions are offered. EOF, invalid input and turn
exhaustion preserve the last verified save without granting resources.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_tile_survival import (
    MAX_BYTES, MAX_STEPS, _action, _advance, _json, export_survival,
    import_survival, new_survival, original_survival, verify_survival,
)
from skeleton.game.gameplay.scene_tile_survival_route import legal_survival_actions
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_INPUT_BYTES = 128 * 1024
MAX_INVALID_ATTEMPTS = 3
MAX_CHECKPOINT_INTERVAL = 64


def parse_player_action(line: str) -> dict[str, Any]:
    if type(line) is not str:
        raise SceneTravelError("survival player action must be text")
    try:
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise SceneTravelError("survival player input exceeds byte budget")
    except UnicodeError as exc:
        raise SceneTravelError("invalid survival input encoding") from exc
    raw = line.strip()
    if raw.startswith("{"):
        return _action(_json(raw))
    parts = raw.split()
    if parts == ["rest"]:
        return {"kind": "rest"}
    if len(parts) == 1 and parts[0] in ("north", "south", "east", "west"):
        return {"kind": "tile", "action": {
            "kind": "move", "direction": parts[0],
        }}
    if len(parts) == 2 and parts[0] in ("collect", "travel"):
        return {"kind": "tile", "action": {
            "kind": parts[0],
            "pickup_id" if parts[0] == "collect" else "exit_id": parts[1],
        }}
    raise SceneTravelError(
        "use north/south/east/west, collect PICKUP, travel EXIT, rest or JSON"
    )


def _emit(writer: Any, event: dict[str, Any]) -> None:
    writer.write(json.dumps(
        event, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=False,
    ) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    saved = verify_survival(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"], "session": saved,
    })


def play_survival(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8, max_turns: int = 128,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one survival source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL:
        raise SceneTravelError("invalid survival checkpoint interval")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_STEPS:
        raise SceneTravelError("invalid interactive survival turn budget")
    current = new_survival(source) if session is None else verify_survival(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or expected_source_digest != current["source_digest"]):
            raise SceneTravelError("survival source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    initial_tick = current["state"]["tick"]
    _emit(writer, {
        "event": "started", "tick": initial_tick,
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        if current["state"]["tick"] - initial_tick >= max_turns:
            _checkpoint(writer, current, "turn_budget")
            raise SceneTravelError("survival turn budget exhausted; checkpoint emitted")
        state = current["state"]
        tile = state["tile"]["state"]
        available = legal_survival_actions(current)
        _emit(writer, {
            "event": "prompt", "tick": state["tick"],
            "scene_id": tile["scene"]["state"]["scene_id"],
            "position": tile["position"], "health": state["health"],
            "food": state["food"], "used_camps": state["used_camps"],
            "available_actions": available,
            "state_digest": current["state_digest"],
        })
        if not available:
            _checkpoint(writer, current, "no_legal_action")
            raise SceneTravelError("no legal survival action; checkpoint emitted")
        for attempt in range(MAX_INVALID_ATTEMPTS):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("survival input ended; checkpoint emitted")
            try:
                action = parse_player_action(line)
                if action not in available:
                    raise SceneTravelError("survival action unavailable in current state")
                updated = _advance(current, action)
            except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
                _emit(writer, {
                    "event": "invalid", "attempt": attempt + 1,
                    "error": str(exc),
                })
                if attempt + 1 == MAX_INVALID_ATTEMPTS:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise SceneTravelError(
                        "survival input retries exhausted; checkpoint emitted"
                    ) from exc
                continue
            current = updated
            _emit(writer, {
                "event": "accepted", "tick": current["state"]["tick"],
                "state_digest": current["state_digest"],
                "action_receipt": current["journal"][-1]["receipt"],
            })
            if current["state"]["tick"] % checkpoint_every == 0:
                _checkpoint(writer, current, "interval")
            break
    saved = verify_survival(current)
    bundle = export_survival(saved)
    if import_survival(bundle) != saved:
        raise SceneTravelError("survival terminal export roundtrip mismatch")
    _checkpoint(writer, saved, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": saved["state"]["phase"],
        "health": saved["state"]["health"], "food": saved["state"]["food"],
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"], "bundle": bundle,
    })
    return saved


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-survival-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("demo-script", help="replay the original authored route without reading stdin")
    play = sub.add_parser("play")
    play.add_argument("--source-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    for p in (play, resume):
        p.add_argument("--expected-source-digest")
        p.add_argument("--checkpoint-every", type=int, default=8)
        p.add_argument("--max-turns", type=int, default=128)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_survival()
            result = play_survival(source=source)
        elif args.command == "demo-script":
            source, actions = original_survival()
            # The fixture actions still pass through real legal-action checks,
            # replay verification and terminal export, never a fabricated win.
            scripted = io.StringIO("".join(
                json.dumps(action, sort_keys=True, separators=(",", ":")) + "\n"
                for action in actions
            ))
            result = play_survival(source=source, input_stream=scripted)
        else:
            options = {
                "expected_source_digest": args.expected_source_digest,
                "checkpoint_every": args.checkpoint_every,
                "max_turns": args.max_turns,
            }
            if args.command == "play":
                result = play_survival(
                    source=_json(args.source_json), **options,
                )
            else:
                result = play_survival(
                    session=_json(args.session_json), **options,
                )
        return 0 if result["state"]["phase"] == "won" else 1
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
