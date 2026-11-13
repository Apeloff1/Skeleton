"""Interactive offline NPC scene play with bounded input and save checkpoints.

The JSON-line terminal is an adapter to the same canonical scene and NPC
transition engine used by replay, solver and portable export. It never reads
arbitrary files or executes author-controlled scripts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_npc_encounter import (
    _step, new_encounter, original_encounter, verify_encounter,
)
from skeleton.game.gameplay.scene_npc_solver import _candidates
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_INPUT_BYTES = 128 * 1024
MAX_CHECKPOINT_INTERVAL = 64


def parse_player_action(line: str) -> dict[str, Any]:
    """Parse explicit offline verbs or bounded duplicate-key-safe JSON."""
    if type(line) is not str:
        raise SceneTravelError("NPC player action must be text")
    try:
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise SceneTravelError("NPC player action exceeds input budget")
    except UnicodeError as exc:
        raise SceneTravelError("invalid NPC player action encoding") from exc
    raw = line.strip()
    if raw.startswith("{"):
        value = _strict_json(raw, "NPC player action", max_bytes=MAX_INPUT_BYTES)
        if type(value) is not dict:
            raise SceneTravelError("NPC player action must be object")
        return value
    parts = raw.split()
    if len(parts) == 3 and parts[0] == "talk":
        return {"kind": "talk", "npc_id": parts[1], "offer_id": parts[2]}
    if len(parts) == 2 and parts[0] in ("collect", "travel", "finish"):
        if parts[0] == "finish":
            return {"kind": "finish", "ending_id": parts[1]}
        key = "pickup_id" if parts[0] == "collect" else "exit_id"
        return {"kind": "scene", "action": {"kind": parts[0], key: parts[1]}}
    raise SceneTravelError("use talk NPC OFFER, collect PICKUP, travel EXIT, finish ENDING or JSON")


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    })


def play_encounter(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one NPC source or saved session")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL:
        raise SceneTravelError("NPC checkpoint interval outside 1..64")
    current = new_encounter(source) if session is None else verify_encounter(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or current["source_digest"] != expected_source_digest):
            raise SceneTravelError("NPC source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
        "tick": current["state"]["tick"],
    })
    while current["state"]["phase"] == "active":
        scene = current["state"]["scene"]["state"]
        if scene["phase"] == "active":
            available_actions = _candidates(current, "")
        else:
            available_actions = [
                {"kind": "finish", "ending_id": ending["id"]}
                for ending in current["source"]["endings"]
                if ending["scene_phase"] == scene["phase"]
                and set(ending["requires_flags"]) <= set(current["state"]["flags"])
                and current["state"]["reputation"] >= ending["min_reputation"]
            ]
        _emit(writer, {
            "event": "prompt", "tick": current["state"]["tick"],
            "scene_id": scene["scene_id"], "scene_phase": scene["phase"],
            "flags": current["state"]["flags"],
            "reputation": current["state"]["reputation"],
            "choices": current["state"]["choices"],
            "available_actions": available_actions,
            "state_digest": current["state_digest"],
        })
        for attempt in range(3):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("NPC input ended; verified checkpoint emitted")
            try:
                action = parse_player_action(line)
                next_session = _step(current, action)
            except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
                _emit(writer, {
                    "event": "invalid", "attempt": attempt + 1,
                    "error": str(exc),
                })
                if attempt == 2:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise SceneTravelError(
                        "NPC input retries exhausted; verified checkpoint emitted"
                    ) from exc
                continue
            current = next_session
            _emit(writer, {
                "event": "accepted", "tick": current["state"]["tick"],
                "state_digest": current["state_digest"],
                "action_receipt": current["journal"][-1]["receipt"],
            })
            if current["state"]["tick"] % checkpoint_every == 0:
                _checkpoint(writer, current, "interval")
            break
    current = verify_encounter(current)
    _checkpoint(writer, current, "terminal")
    _emit(writer, {
        "event": "terminal", "ending": current["state"]["ending"],
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-npc-play")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--resume-json")
    parser.add_argument("--source-digest")
    parser.add_argument("--checkpoint-every", type=int, default=8)
    try:
        args = parser.parse_args(list(argv))
        saved = (_strict_json(args.resume_json, "NPC save")
                 if args.resume_json is not None else None)
        source = (
            original_encounter() if args.demo else
            _strict_json(args.source_json, "NPC source")
            if args.source_json is not None else None
        )
        play_encounter(
            source, session=saved,
            expected_source_digest=args.source_digest,
            checkpoint_every=args.checkpoint_every,
        )
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
