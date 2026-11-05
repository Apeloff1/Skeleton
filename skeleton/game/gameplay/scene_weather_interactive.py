"""Stream-based weather gameplay with verified restartable checkpoints.

Commands are parsed into the canonical weather reducer; no second game state,
filesystem access, network call or untrusted code execution is introduced.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_tile_walk import _json
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id
from skeleton.game.gameplay.scene_weather import (
    _advance, forecast, new_weather, original_weather, verify_weather,
)

MAX_COMMAND_BYTES = 8192
MAX_RETRIES = 3


def parse_weather_command(raw: str) -> dict[str, Any]:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise SceneTravelError("weather command exceeds input budget")
    line = raw.strip()
    if line.startswith("{"):
        action = _json(line)
        if type(action) is not dict:
            raise SceneTravelError("weather command must be an object")
        return action
    words = line.split()
    if words == ["rest"]:
        return {"kind": "survival", "action": {"kind": "rest"}}
    if words == ["unequip"]:
        return {"kind": "unequip"}
    if len(words) == 2:
        kind, ident = words
        if kind == "equip":
            return {"kind": "equip", "gear_id": _id(ident, "gear id")}
        if kind == "move":
            return {"kind": "survival", "action": {
                "kind": "tile", "action": {"kind": "move", "direction": ident}}}
        if kind in ("collect", "travel"):
            return {"kind": "survival", "action": {
                "kind": "tile", "action": {
                    "kind": kind,
                    "pickup_id" if kind == "collect" else "exit_id": _id(ident, "interaction"),
                }}}
    raise SceneTravelError("use move/collect/travel/equip ID, rest, unequip or JSON")


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    })


def _board(session: dict[str, Any]) -> dict[str, Any]:
    state = session["state"]
    tile = state["survival"]["state"]["tile"]["state"]
    scene_id = tile["scene"]["state"]["scene_id"]
    return {
        "event": "weather", "tick": state["tick"],
        "scene_id": scene_id, "position": tile["position"],
        "health": state["health"], "stamina": state["stamina"],
        "food": state["survival"]["state"]["food"],
        "owned_gear": state["owned_gear"], "equipped": state["equipped"],
        "forecast_next": forecast(
            session["source"], scene_id, min(state["tick"] + 1, 256)),
        "phase": state["phase"], "state_digest": session["state_digest"],
    }


def play_weather(source: Any = None, *, session: Any = None,
                 expected_source_digest: str | None = None,
                 checkpoint_every: int = 8,
                 input_stream: Any = None,
                 output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one weather source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("invalid weather checkpoint interval")
    current = new_weather(source) if session is None else verify_weather(session)
    if expected_source_digest is not None and (
        type(expected_source_digest) is not str or
        re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None or
        expected_source_digest != current["source_digest"]
    ):
        raise SceneTravelError("weather source digest does not match trusted input")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        _emit(writer, _board(current))
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_COMMAND_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("weather input ended; verified checkpoint emitted")
            try:
                action = parse_weather_command(line)
                updated = _advance(current, action)
            except (SceneTravelError, ValueError, TypeError, KeyError) as exc:
                _emit(writer, {
                    "event": "rejected", "attempt": attempt + 1,
                    "reason": str(exc), "state_digest": current["state_digest"],
                })
                if attempt + 1 == MAX_RETRIES:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise SceneTravelError("weather input retry budget exhausted") from exc
                continue
            current = updated
            _emit(writer, {
                "event": "accepted", "tick": current["state"]["tick"],
                "state_digest": current["state_digest"],
                "receipt": current["journal"][-1]["receipt"],
            })
            if current["state"]["tick"] % checkpoint_every == 0:
                _checkpoint(writer, current, "interval")
            break
    _checkpoint(writer, current, "terminal")
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("demo-script")
    p = sub.add_parser("play")
    p.add_argument("--source-json")
    p.add_argument("--session-json")
    p.add_argument("--expected-source-digest")
    p.add_argument("--checkpoint-every", type=int, default=8)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_weather()
            result = play_weather(source=source)
        elif args.command == "demo-script":
            from io import StringIO
            source, actions = original_weather()
            script = "".join(json.dumps(action, sort_keys=True) + "\n"
                             for action in actions)
            result = play_weather(source=source, input_stream=StringIO(script))
        else:
            if bool(args.source_json) == bool(args.session_json):
                raise SceneTravelError("supply source or session JSON")
            result = play_weather(
                source=_json(args.source_json) if args.source_json else None,
                session=_json(args.session_json) if args.session_json else None,
                expected_source_digest=args.expected_source_digest,
                checkpoint_every=args.checkpoint_every)
        return 0 if result["state"]["phase"] == "won" else 2
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
