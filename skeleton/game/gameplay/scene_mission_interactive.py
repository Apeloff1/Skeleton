"""Replay-verified interactive mission play over canonical scene/quest runtime.

Player input never grants rewards. Every accepted move uses the canonical
director, and interruption produces a replayable checkpoint for recovery.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_mission import (
    MAX_ACTIONS, MAX_BYTES, MAX_SOURCE_BYTES, _action, _advance,
    export_mission, import_mission, new_mission, original_mission, verify_mission,
)
from skeleton.game.gameplay.scene_mission_solver import _options
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_INPUT_BYTES = 128 * 1024
MAX_CHECKPOINT_INTERVAL = 64
MAX_INVALID_ATTEMPTS = 3


def parse_player_action(line: str) -> dict[str, Any]:
    """Parse bounded explicit verbs or duplicate-key-safe JSON actions."""
    if type(line) is not str:
        raise SceneTravelError("mission player action must be text")
    try:
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise SceneTravelError("mission player action exceeds input budget")
    except UnicodeError as exc:
        raise SceneTravelError("invalid mission action encoding") from exc
    raw = line.strip()
    if raw.startswith("{"):
        return _action(_strict_json(raw, "mission action", max_bytes=MAX_INPUT_BYTES))
    parts = raw.split()
    if len(parts) == 3 and parts[0] == "choose":
        return _action({"kind": "choose", "choice_id": parts[1], "option_id": parts[2]})
    if len(parts) == 2 and parts[0] in ("collect", "travel", "finish"):
        if parts[0] == "finish":
            return _action({"kind": "finish", "ending_id": parts[1]})
        key = "pickup_id" if parts[0] == "collect" else "exit_id"
        return _action({"kind": "scene", "action": {"kind": parts[0], key: parts[1]}})
    raise SceneTravelError(
        "use choose CHOICE OPTION, collect PICKUP, travel EXIT, finish ENDING or JSON"
    )


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            allow_nan=False, ensure_ascii=False) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    verified = verify_mission(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"], "session": verified,
    })


def legal_actions(session: Any) -> list[dict[str, Any]]:
    """Filter solver candidates through the real runtime, never guess legality."""
    current = verify_mission(session)
    available = []
    for action in _options(current):
        try:
            _advance(current, action)
        except SceneTravelError:
            continue
        available.append(action)
    return available


def play_mission(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8, max_turns: int = 128,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL:
        raise SceneTravelError("mission checkpoint interval outside 1..64")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_ACTIONS:
        raise SceneTravelError("mission turn budget outside 1..512")
    current = new_mission(source) if session is None else verify_mission(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or current["source_digest"] != expected_source_digest):
            raise SceneTravelError("mission source does not match trusted digest")
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
            raise SceneTravelError("mission turn budget exhausted; checkpoint emitted")
        state = current["state"]
        scene = state["scene"]["state"]
        available = legal_actions(current)
        _emit(writer, {
            "event": "prompt", "tick": state["tick"],
            "scene_id": scene["scene_id"], "scene_phase": scene["phase"],
            "inventory": scene["inventory"], "visited": scene["visited"],
            "missions": state["missions"], "choices": state["choices"],
            "reputation": state["reputation"],
            "available_actions": available, "state_digest": current["state_digest"],
        })
        if not available:
            _checkpoint(writer, current, "no_legal_action")
            raise SceneTravelError("no legal mission action; checkpoint emitted")
        for attempt in range(MAX_INVALID_ATTEMPTS):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("mission input ended; checkpoint emitted")
            try:
                action = parse_player_action(line)
                if action not in available:
                    raise SceneTravelError("action unavailable in current mission state")
                updated = _advance(current, action)
            except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
                _emit(writer, {"event": "invalid", "attempt": attempt + 1,
                               "error": str(exc)})
                if attempt + 1 == MAX_INVALID_ATTEMPTS:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise SceneTravelError("mission input retries exhausted; checkpoint emitted") from exc
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
    current = verify_mission(current)
    bundle = export_mission(current)
    if import_mission(bundle) != current:
        raise SceneTravelError("terminal mission export roundtrip mismatch")
    _checkpoint(writer, current, "terminal")
    _emit(writer, {
        "event": "terminal", "ending": current["state"]["ending"],
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"], "bundle": bundle,
    })
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-play")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--resume-json")
    parser.add_argument("--source-digest")
    parser.add_argument("--checkpoint-every", type=int, default=8)
    parser.add_argument("--max-turns", type=int, default=128)
    args = parser.parse_args(list(argv))
    try:
        saved = (_strict_json(args.resume_json, "mission checkpoint", max_bytes=MAX_BYTES)
                 if args.resume_json is not None else None)
        source = (original_mission() if args.demo else
                  _strict_json(args.source_json, "mission source", max_bytes=MAX_SOURCE_BYTES)
                  if args.source_json is not None else None)
        play_mission(
            source, session=saved, expected_source_digest=args.source_digest,
            checkpoint_every=args.checkpoint_every, max_turns=args.max_turns,
        )
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
