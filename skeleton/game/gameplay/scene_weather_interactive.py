"""Accessible offline weather-gated scene play with durable checkpoints.

Every player verb goes through the canonical weather and scene engines.
No user text is executed as code, and no checkpoint is written to disk by
this module. EOF and invalid commands emit the latest replay-valid save.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from skeleton.game.gameplay.scene_travel import (
    MAX_JSON_BYTES, SceneTravelError, _json,
)
from skeleton.game.gameplay.scene_weather import (
    _action, _advance, _export, new_session, original_weather_demo,
    verify_session,
)

MAX_ATTEMPTS = 3


def parse_weather_command(line: Any) -> dict[str, Any]:
    """Parse human-readable collect/travel/wait or strict canonical JSON."""
    if type(line) is not str:
        raise SceneTravelError("weather player command must be text")
    try:
        size = len(line.encode("utf-8"))
    except UnicodeError as exc:
        raise SceneTravelError("invalid weather player command encoding") from exc
    if size > MAX_JSON_BYTES:
        raise SceneTravelError("weather player command exceeds 128 KiB")
    value = line.strip()
    if value.startswith("{"):
        return _action(_json(value, "weather player action"))
    words = value.split()
    if words == ["wait"]:
        return {"kind": "wait"}
    if len(words) == 2 and words[0] in ("collect", "travel"):
        field = "pickup_id" if words[0] == "collect" else "exit_id"
        return _action({"kind": "scene", "action": {
            "kind": words[0], field: words[1],
        }})
    raise SceneTravelError("use wait, collect PICKUP, travel EXIT or JSON")


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _export(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    })


def _view(session: dict[str, Any]) -> dict[str, Any]:
    source, state = session["source"], session["state"]
    scene_state = state["scene"]["state"]
    scene_id = scene_state["scene_id"]
    scene = next(item for item in source["world"]["scenes"]
                 if item["id"] == scene_id)
    gates = {
        (item["scene_id"], item["exit_id"]): set(item["conditions"])
        for item in source["blocked_exits"]
    }
    inventory = set(scene_state["inventory"])
    exits = [{
        "id": edge["id"], "to": edge["to"],
        "requires_item": edge["requires_item"],
        "blocked_by_weather": state["weather"] in gates.get(
            (scene_id, edge["id"]), set()),
        "missing_item": (
            edge["requires_item"] is not None
            and edge["requires_item"] not in inventory
        ),
    } for edge in scene["exits"]]
    collected = set(scene_state["collected"])
    pickups = [
        item for item in scene["pickups"]
        if f'{scene_id}:{item["id"]}' not in collected
    ]
    return {
        "event": "scene", "scene_id": scene_id,
        "tick": state["tick"], "weather": state["weather"],
        "exits": exits, "pickups": pickups,
        "inventory": scene_state["inventory"],
        "state_digest": session["state_digest"],
        "commands": ["wait", "collect PICKUP", "travel EXIT"],
    }


def play_weather(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 4,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    """Play until a terminal scene, or emit a verified checkpoint on input loss."""
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one weather source or save")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("weather checkpoint interval outside 1..64")
    current = new_session(source) if session is None else verify_session(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or current["source_digest"] != expected_source_digest):
            raise SceneTravelError("weather source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        _emit(writer, _view(current))
        for attempt in range(MAX_ATTEMPTS):
            line = reader.readline(MAX_JSON_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("weather input ended; verified checkpoint emitted")
            try:
                action = parse_weather_command(line)
                updated = _advance(current, action)
            except SceneTravelError as exc:
                _emit(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": MAX_ATTEMPTS - attempt - 1,
                })
                if attempt == MAX_ATTEMPTS - 1:
                    _checkpoint(writer, current, "invalid_commands")
                    raise SceneTravelError(
                        "three invalid weather commands; verified checkpoint emitted"
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
        "weather": current["state"]["weather"],
        "scene_id": current["state"]["scene"]["state"]["scene_id"],
        "state_digest": current["state_digest"],
    })
    return current


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-play")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--source-json")
    source.add_argument("--session-json")
    parser.add_argument("--expected-digest")
    parser.add_argument("--checkpoint-every", type=int, default=4)
    args = parser.parse_args(list(argv))
    try:
        authored = (
            original_weather_demo()[0] if args.demo else
            _json(args.source_json, "weather source")
            if args.source_json is not None else None
        )
        saved = (
            _json(args.session_json, "weather save")
            if args.session_json is not None else None
        )
        play_weather(
            authored, session=saved,
            expected_source_digest=args.expected_digest,
            checkpoint_every=args.checkpoint_every,
        )
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
