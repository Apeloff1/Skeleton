"""Player-facing evacuation turns with legal action previews and checkpoints.

JSON-lines input is deliberately bounded. No untrusted source can execute code,
open files, make network calls or mint NPCs or rewards.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_evacuation import (
    MAX_BYTES, _bounded, advance_evacuation, demo_actions,
    new_evacuation, original_evacuation, verify_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_board import inspect_evacuation
from skeleton.game.gameplay.scene_travel import SceneTravelError


def play_evacuation(source: Any, actions: Any, *,
                    checkpoint: Any = None) -> dict[str, Any]:
    if type(actions) is not list:
        raise SceneTravelError("evacuation play actions must be a list")
    saved = new_evacuation(source) if checkpoint is None else verify_evacuation(checkpoint)
    if saved["source_digest"] != dig(new_evacuation(source)["source"]):
        raise SceneTravelError("evacuation play checkpoint source mismatch")
    frames = [inspect_evacuation(saved)]
    if len(actions) + len(saved["journal"]) > saved["source"]["turn_budget"]:
        raise SceneTravelError("evacuation play exceeds authored turn budget")
    for action in actions:
        if action not in frames[-1]["legal_actions"]:
            raise SceneTravelError("player action not legal at this checkpoint")
        saved = advance_evacuation(saved, action)
        frames.append(inspect_evacuation(saved))
    result = {
        "schema_version": "skeleton.scene_evacuation_play.v1",
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"],
        "phase": saved["state"]["phase"], "frames": frames,
        "checkpoint": saved,
    }
    result["receipt"] = dig({
        "source_digest": result["source_digest"],
        "state_digest": result["state_digest"],
        "frame_receipts": [frame["receipt"] for frame in frames],
    })
    _bounded(result)
    return result


def _live(source: Any, checkpoint: Any = None) -> dict[str, Any]:
    saved = new_evacuation(source) if checkpoint is None else verify_evacuation(checkpoint)
    if saved["source_digest"] != dig(new_evacuation(source)["source"]):
        raise SceneTravelError("evacuation live checkpoint source mismatch")
    while saved["state"]["phase"] == "active":
        board = inspect_evacuation(saved)
        print(json.dumps({"board": board, "checkpoint": saved}, sort_keys=True),
              flush=True)
        # Bounded read prevents an interactive client from exhausting memory
        # before the strict JSON parser can enforce the byte limit.
        raw = sys.stdin.readline(MAX_BYTES + 1)
        if not raw or raw.strip() == "quit":
            break
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise SceneTravelError("player action exceeds input byte budget")
        action = _strict_json(raw, "player action", max_bytes=MAX_BYTES)
        if action not in board["legal_actions"]:
            raise SceneTravelError("player action not legal at this checkpoint")
        saved = advance_evacuation(saved, action)
    return saved


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-evacuation-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    script = sub.add_parser("script")
    script.add_argument("--source-json", required=True)
    script.add_argument("--actions-json", required=True)
    script.add_argument("--session-json")
    live = sub.add_parser("live")
    live.add_argument("--source-json")
    live.add_argument("--session-json")
    args = parser.parse_args(list(argv))
    try:
        parse = lambda raw: _strict_json(raw, "evacuation play", max_bytes=MAX_BYTES)
        if args.command == "demo":
            result = play_evacuation(original_evacuation(), demo_actions())
        elif args.command == "script":
            result = play_evacuation(
                parse(args.source_json), parse(args.actions_json),
                checkpoint=(parse(args.session_json)
                            if args.session_json is not None else None),
            )
        else:
            source = (parse(args.source_json) if args.source_json is not None
                      else original_evacuation())
            result = _live(source, (parse(args.session_json)
                                    if args.session_json is not None else None))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
