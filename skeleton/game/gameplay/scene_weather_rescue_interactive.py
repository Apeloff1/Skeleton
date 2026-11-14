"""Accessible NPC rescue play with verified EOF and invalid-command checkpoints."""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from skeleton.game.gameplay.scene_travel import (
    MAX_JSON_BYTES, SceneTravelError, _json,
)
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_rescue import (
    _action, _advance, new_rescue, original_rescue, verify_rescue,
)

MAX_ATTEMPTS = 3


def parse_rescue_command(line: Any) -> dict[str, Any]:
    if type(line) is not str:
        raise SceneTravelError("rescue player command must be text")
    try:
        size = len(line.encode("utf-8"))
    except UnicodeError as exc:
        raise SceneTravelError("invalid rescue player command encoding") from exc
    if size > MAX_JSON_BYTES:
        raise SceneTravelError("rescue player command exceeds 128 KiB")
    text = line.strip()
    if text.startswith("{"):
        return _action(_json(text, "rescue player action"))
    words = text.split()
    if words == ["wait"]:
        return {"kind": "weather", "action": {"kind": "wait"}}
    if len(words) == 2:
        verb, identifier = words
        if verb in ("rescue", "shelter"):
            return _action({"kind": verb, "npc_id": identifier})
        if verb in ("collect", "travel"):
            return _action({
                "kind": "weather", "action": {
                    "kind": "scene", "action": {
                        "kind": verb,
                        "pickup_id" if verb == "collect" else "exit_id": identifier,
                    },
                },
            })
    raise SceneTravelError("use rescue NPC, shelter NPC, collect PICKUP, travel EXIT, wait or JSON")


def _emit(writer: Any, value: dict[str, Any]) -> None:
    writer.write(json.dumps(value, sort_keys=True, separators=(",", ":"),
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
    weather = session["weather_session"]
    scene_state = weather["state"]["scene"]["state"]
    scene_id = scene_state["scene_id"]
    current = next(scene for scene in source["weather"]["world"]["scenes"]
                   if scene["id"] == scene_id)
    blocked = {
        (rule["scene_id"], rule["exit_id"]): set(rule["conditions"])
        for rule in source["weather"]["blocked_exits"]
    }
    inventory = set(scene_state["inventory"])
    collected = set(scene_state["collected"])
    exits = [{
        "id": edge["id"], "to": edge["to"],
        "blocked_by_weather": weather["state"]["weather"] in blocked.get(
            (scene_id, edge["id"]), set(),
        ),
        "missing_item": (
            edge["requires_item"] is not None
            and edge["requires_item"] not in inventory
        ),
    } for edge in current["exits"]]
    pickups = [
        item for item in current["pickups"]
        if scene_id + ":" + item["id"] not in collected
    ]
    available = []
    for npc in source["npcs"]:
        status = state["npcs"][npc["npc_id"]]["status"]
        if status == "waiting" and npc["origin_scene"] == scene_id:
            available.append("rescue " + npc["npc_id"])
        if status == "escorting" and npc["shelter_scene"] == scene_id:
            available.append("shelter " + npc["npc_id"])
    return {
        "event": "scene", "scene_id": scene_id,
        "weather": weather["state"]["weather"],
        "tick": state["tick"], "phase": state["phase"],
        "earned": state["earned"], "npcs": state["npcs"],
        "exits": exits, "pickups": pickups,
        "inventory": scene_state["inventory"],
        "available_rescue_commands": available,
        "commands": ["rescue NPC", "shelter NPC", "collect PICKUP", "travel EXIT", "wait"],
        "state_digest": session["state_digest"],
    }


def play_rescue_interactive(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 4,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one rescue source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("rescue checkpoint interval outside 1..64")
    current = new_rescue(source) if session is None else verify_rescue(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or current["source_digest"] != expected_source_digest):
            raise SceneTravelError("rescue source does not match trusted digest")
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
                raise SceneTravelError("rescue input ended; verified checkpoint emitted")
            try:
                action = parse_rescue_command(line)
                updated = _advance(current, action)
            except SceneTravelError as exc:
                _emit(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": MAX_ATTEMPTS - attempt - 1,
                })
                if attempt == MAX_ATTEMPTS - 1:
                    _checkpoint(writer, current, "invalid_commands")
                    raise SceneTravelError(
                        "three invalid rescue commands; verified checkpoint emitted"
                    ) from exc
            else:
                current = updated
                _emit(writer, {
                    "event": "accepted", "action": action,
                    "tick": current["state"]["tick"],
                    "state_digest": current["state_digest"],
                    "earned": current["state"]["earned"],
                })
                break
        if (current["state"]["phase"] == "active"
                and current["state"]["tick"] % checkpoint_every == 0):
            _checkpoint(writer, current, "interval")
    _checkpoint(writer, current, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": current["state"]["phase"],
        "earned": current["state"]["earned"],
        "npcs": current["state"]["npcs"],
        "state_digest": current["state_digest"],
    })
    return current


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-rescue-play")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--resume-json")
    parser.add_argument("--expected-source-digest")
    parser.add_argument("--checkpoint-every", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.demo:
            source, _ = original_rescue()
            result = play_rescue_interactive(
                source, expected_source_digest=args.expected_source_digest,
                checkpoint_every=args.checkpoint_every,
            )
        elif args.source_json is not None:
            result = play_rescue_interactive(
                _json(args.source_json, "rescue source"),
                expected_source_digest=args.expected_source_digest,
                checkpoint_every=args.checkpoint_every,
            )
        else:
            result = play_rescue_interactive(
                session=_json(args.resume_json, "rescue checkpoint"),
                expected_source_digest=args.expected_source_digest,
                checkpoint_every=args.checkpoint_every,
            )
        return 0 if result["state"]["phase"] == "won" else 3
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
