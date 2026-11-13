"""Interactive, restartable survival campaigns with fail-closed checkpoints."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_survival_campaign import (
    _advance, _json, export_campaign, import_campaign,
    new_campaign, original_campaign, verify_campaign,
)
from skeleton.game.gameplay.scene_tile_survival_interactive import (
    MAX_INPUT_BYTES, MAX_INVALID_ATTEMPTS, parse_player_action,
)
from skeleton.game.gameplay.scene_tile_survival_route import legal_survival_actions
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_TURNS = 512


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    verified = verify_campaign(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "state_digest": verified["state_digest"], "session": verified,
    })


def play_campaign(source: Any = None, *, session: Any = None,
                  expected_source_digest: str | None = None,
                  checkpoint_every: int = 8, max_turns: int = 128,
                  input_stream: Any = None,
                  output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one campaign source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("invalid campaign checkpoint interval")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_TURNS:
        raise SceneTravelError("invalid campaign turn budget")
    current = new_campaign(source) if session is None else verify_campaign(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or expected_source_digest != current["source_digest"]):
            raise SceneTravelError("campaign source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    first_tick = current["state"]["tick"]
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"], "tick": first_tick,
    })
    while current["state"]["phase"] == "active":
        state = current["state"]
        if state["tick"] - first_tick >= max_turns:
            _checkpoint(writer, current, "turn_budget")
            raise SceneTravelError("campaign turn budget exhausted; checkpoint emitted")
        available = legal_survival_actions(state["stage"])
        _emit(writer, {
            "event": "prompt", "tick": state["tick"],
            "stage_id": current["source"]["stages"][state["stage_index"]]["stage_id"],
            "score": state["score"], "completed": state["completed"],
            "health": state["stage"]["state"]["health"],
            "food": state["stage"]["state"]["food"],
            "available_actions": available,
            "state_digest": current["state_digest"],
        })
        if not available:
            _checkpoint(writer, current, "no_legal_action")
            raise SceneTravelError("no legal campaign action; checkpoint emitted")
        for attempt in range(MAX_INVALID_ATTEMPTS):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("campaign input ended; checkpoint emitted")
            try:
                action = parse_player_action(line)
                if action not in available:
                    raise SceneTravelError("campaign action unavailable")
                updated = _advance(current, action)
            except (SceneTravelError, ValueError, KeyError,
                    TypeError, RecursionError) as exc:
                _emit(writer, {
                    "event": "invalid", "attempt": attempt + 1,
                    "error": str(exc),
                })
                if attempt + 1 == MAX_INVALID_ATTEMPTS:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise SceneTravelError(
                        "campaign input retries exhausted; checkpoint emitted"
                    ) from exc
                continue
            previous_index = state["stage_index"]
            current = updated
            _emit(writer, {
                "event": "accepted", "tick": current["state"]["tick"],
                "state_digest": current["state_digest"],
                "action_receipt": current["journal"][-1]["receipt"],
            })
            if current["state"]["stage_index"] != previous_index:
                _checkpoint(writer, current, "stage_completed")
            elif current["state"]["tick"] % checkpoint_every == 0:
                _checkpoint(writer, current, "interval")
            break
    saved = verify_campaign(current)
    bundle = export_campaign(saved)
    if import_campaign(bundle) != saved:
        raise SceneTravelError("campaign terminal export roundtrip mismatch")
    _checkpoint(writer, saved, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": saved["state"]["phase"],
        "score": saved["state"]["score"],
        "state_digest": saved["state_digest"], "bundle": bundle,
    })
    return saved


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-survival-campaign-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
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
            source, _ = original_campaign()
            result = play_campaign(source)
        else:
            options = {
                "expected_source_digest": args.expected_source_digest,
                "checkpoint_every": args.checkpoint_every,
                "max_turns": args.max_turns,
            }
            if args.command == "play":
                result = play_campaign(source=_json(args.source_json), **options)
            else:
                result = play_campaign(session=_json(args.session_json), **options)
        return 0 if result["state"]["phase"] == "won" else 1
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
