"""Interactive player selection of replay-proven offline market futures.

The preview is a read-only decision board until an accepted candidate is
explicitly selected. Failed input never changes the canonical game checkpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, TextIO

from skeleton.game.gameplay.scene_market import (
    _bounded, _json, export_market,
)
from skeleton.game.gameplay.scene_market_fork import (
    choose_market_fork, export_market_fork, original_fork,
    verify_market_fork,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_INPUT = 4096
MAX_RETRIES = 3


def _emit(writer: TextIO, payload: dict[str, Any]) -> None:
    _bounded(payload)
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def play_market_fork(report: Any, *, reader: TextIO | None = None,
                     writer: TextIO | None = None) -> dict[str, Any]:
    """Present alternatives and commit exactly one validated player decision."""
    canonical = verify_market_fork(report)
    input_stream = sys.stdin if reader is None else reader
    output_stream = sys.stdout if writer is None else writer
    board = {
        "event": "fork_board",
        "source_digest": canonical["source_digest"],
        "checkpoint_state_digest": canonical["checkpoint_state_digest"],
        "heuristic_candidate": canonical["heuristic_candidate"],
        "qualification": canonical["qualification"],
        "choices": [{
            "candidate_id": item["candidate_id"],
            "status": item["status"],
            "phase": item["phase"],
            "blocked_step": item["blocked_step"],
            "blocked_reason": item["blocked_reason"],
            "credits": item["credits"],
            "reputation": item["reputation"],
        } for item in canonical["outcomes"]],
    }
    _emit(output_stream, board)
    for attempt in range(MAX_RETRIES):
        raw = input_stream.readline(MAX_INPUT + 1)
        if not raw or len(raw) > MAX_INPUT:
            _emit(output_stream, {
                "event": "checkpoint",
                "preview_bundle": export_market_fork(canonical),
            })
            raise SceneTravelError("fork input ended or exceeded budget; preview preserved")
        try:
            command = _json(raw)
            if type(command) is not dict or set(command) != {"candidate_id"}:
                raise SceneTravelError("fork choice requires candidate_id")
            candidate_id = command["candidate_id"]
            selected = choose_market_fork(canonical, candidate_id)
        except (SceneTravelError, KeyError, TypeError, ValueError,
                UnicodeError, RecursionError) as exc:
            _emit(output_stream, {
                "event": "rejected", "error": str(exc),
                "remaining_retries": MAX_RETRIES - attempt - 1,
                "checkpoint_state_digest": canonical["checkpoint_state_digest"],
            })
            if attempt + 1 == MAX_RETRIES:
                _emit(output_stream, {
                    "event": "checkpoint",
                    "preview_bundle": export_market_fork(canonical),
                })
                raise SceneTravelError("fork retries exhausted; preview preserved") from exc
        else:
            _emit(output_stream, {
                "event": "selected", "candidate_id": candidate_id,
                "state_digest": selected["state_digest"],
                "phase": selected["state"]["phase"],
                "game_bundle": export_market(selected),
            })
            return selected
    raise SceneTravelError("fork player input exhausted")


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-fork-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("play").add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        report = original_fork() if args.command == "demo" else _json(args.report_json)
        play_market_fork(report)
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
