"""Bounded interactive convoy play with replayable interruption checkpoints.

The player sees only canonical legal actions. Each accepted input is executed
by the real escort/mission runtime; no prompt can award supplies or endings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_escort import (
    MAX_ACTIONS, MAX_BYTES, _action, _advance, export_escort,
    import_escort, new_escort, original_escort, verify_escort,
)
from skeleton.game.gameplay.scene_escort_solver import _candidates
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_INPUT_BYTES = 128 * 1024
MAX_INVALID_ATTEMPTS = 3
MAX_CHECKPOINT_INTERVAL = 64


def parse_player_action(line: str) -> dict[str, Any]:
    if type(line) is not str:
        raise SceneTravelError("escort player action must be text")
    try:
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise SceneTravelError("escort input exceeds byte budget")
    except UnicodeError as exc:
        raise SceneTravelError("invalid escort input encoding") from exc
    raw = line.strip()
    if raw.startswith("{"):
        return _action(_strict_json(raw, "escort action", max_bytes=MAX_INPUT_BYTES))
    parts = raw.split()
    if parts == ["protect"]:
        return {"kind": "protect"}
    if len(parts) == 3 and parts[0] == "choose":
        return _action({"kind": "mission", "action": {
            "kind": "choose", "choice_id": parts[1], "option_id": parts[2],
        }})
    if len(parts) == 2 and parts[0] in ("collect", "travel", "finish"):
        kind = parts[0]
        nested = (
            {"kind": "finish", "ending_id": parts[1]}
            if kind == "finish" else
            {"kind": "scene", "action": {
                "kind": kind,
                "pickup_id" if kind == "collect" else "exit_id": parts[1],
            }}
        )
        return _action({"kind": "mission", "action": nested})
    raise SceneTravelError(
        "use protect, choose CHOICE OPTION, collect PICKUP, travel EXIT, "
        "finish ENDING or JSON"
    )


def _emit(writer: Any, event: dict[str, Any]) -> None:
    writer.write(json.dumps(event, sort_keys=True, separators=(",", ":"),
                            allow_nan=False, ensure_ascii=False) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    verified = verify_escort(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"], "session": verified,
    })


def legal_actions(payload: Any) -> list[dict[str, Any]]:
    session = verify_escort(payload)
    available = []
    for action in _candidates(session):
        try:
            _advance(session, action)
        except SceneTravelError:
            continue
        available.append(action)
    return available


def play_escort(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8, max_turns: int = 128,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one escort source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL:
        raise SceneTravelError("escort checkpoint interval outside 1..64")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_ACTIONS:
        raise SceneTravelError("escort interactive turn budget outside 1..256")
    current = new_escort(source) if session is None else verify_escort(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or expected_source_digest != current["source_digest"]):
            raise SceneTravelError("escort source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    start_tick = current["state"]["tick"]
    _emit(writer, {
        "event": "started", "tick": start_tick,
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        if current["state"]["tick"] - start_tick >= max_turns:
            _checkpoint(writer, current, "turn_budget")
            raise SceneTravelError("escort turn budget exhausted; checkpoint emitted")
        state = current["state"]
        scene = state["mission"]["state"]["scene"]["state"]
        available = legal_actions(current)
        _emit(writer, {
            "event": "prompt", "tick": state["tick"],
            "scene_id": scene["scene_id"], "integrity": state["integrity"],
            "supplies": state["supplies"], "shielded": state["shielded"],
            "missions": state["mission"]["state"]["missions"],
            "available_actions": available,
            "state_digest": current["state_digest"],
        })
        if not available:
            _checkpoint(writer, current, "no_legal_action")
            raise SceneTravelError("no legal escort action; checkpoint emitted")
        for attempt in range(MAX_INVALID_ATTEMPTS):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("escort input ended; checkpoint emitted")
            try:
                action = parse_player_action(line)
                if action not in available:
                    raise SceneTravelError("escort action unavailable in current state")
                updated = _advance(current, action)
            except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
                _emit(writer, {
                    "event": "invalid", "attempt": attempt + 1, "error": str(exc),
                })
                if attempt + 1 == MAX_INVALID_ATTEMPTS:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise SceneTravelError(
                        "escort input retries exhausted; checkpoint emitted"
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
    verified = verify_escort(current)
    bundle = export_escort(verified)
    if import_escort(bundle) != verified:
        raise SceneTravelError("terminal escort export roundtrip mismatch")
    _checkpoint(writer, verified, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": verified["state"]["phase"],
        "integrity": verified["state"]["integrity"],
        "reward": verified["state"]["reward"],
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"], "bundle": bundle,
    })
    return verified


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-escort-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("demo-script")
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
            result = play_escort(source=original_escort())
        elif args.command == "demo-script":
            from io import StringIO
            from skeleton.game.gameplay.scene_escort import demo_actions
            commands = "".join(
                json.dumps(action, sort_keys=True) + "\n"
                for action in demo_actions()
            )
            result = play_escort(
                source=original_escort(), input_stream=StringIO(commands),
            )
        else:
            opts = {
                "expected_source_digest": args.expected_source_digest,
                "checkpoint_every": args.checkpoint_every,
                "max_turns": args.max_turns,
            }
            parse = lambda raw: _strict_json(raw, "escort play JSON", max_bytes=MAX_BYTES)
            if args.command == "play":
                result = play_escort(source=parse(args.source_json), **opts)
            else:
                result = play_escort(session=parse(args.session_json), **opts)
        return 0 if result["state"]["phase"] == "delivered" else 1
    except (SceneTravelError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
