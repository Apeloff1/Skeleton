"""Local operator CLI: compile and play an original, deterministic game in a browser.

Supports CLI creation and replay verification without importing any untrusted
source scripts, executing an LLM, or contacting a network endpoint.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .contracts import canonical_json
from .playable_compiler import (
    PlayableCompilationError, compile_original_game, export_compiled_project,
)
from .playable_simulation import GameplayError, play_actions
from .playable_world import GameBuildIntent, PlayableWorldError


MAX_INPUT_BYTES = 20_000
MAX_REPLAY_BYTES = 250_000


def _object_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in items:
        if key in obj:
            raise PlayableCompilationError("duplicate input JSON key")
        obj[key] = value
    return obj


def _read_json(path: str, budget: int) -> dict[str, Any]:
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        raise PlayableCompilationError("input must be a regular local file")
    if file.stat().st_size > budget:
        raise PlayableCompilationError("input file too large")
    try:
        data = file.read_bytes()
        if len(data) > budget:
            raise PlayableCompilationError("input file too large")
        value = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_object_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                PlayableCompilationError("nonfinite input value")
            ),
        )
    except (UnicodeDecodeError, ValueError, TypeError, OSError) as exc:
        raise PlayableCompilationError("invalid UTF-8 JSON input") from exc
    if not isinstance(value, dict):
        raise PlayableCompilationError("input must be one JSON object")
    return value


def _intent(data: dict[str, Any]) -> GameBuildIntent:
    fields = {
        "project_id", "title", "subtitle", "seed", "width", "height",
        "levels", "collectibles_per_level", "hazards_per_level",
        "theme", "starting_health",
    }
    if set(data) != fields:
        raise PlayableCompilationError("invalid game intent schema")
    try:
        return GameBuildIntent(**data)
    except (TypeError, ValueError) as exc:
        raise PlayableCompilationError("invalid game intent") from exc


def _actions(data: dict[str, Any], world_digest: str, project_id: str) -> tuple[str, ...]:
    if set(data) != {"schema", "world_digest", "project_id", "actions", "note"}:
        raise PlayableCompilationError("invalid browser replay record")
    if data["schema"] != "skeleton.game_builder.browser_actions.v1":
        raise PlayableCompilationError("unsupported browser replay schema")
    if data["world_digest"] != world_digest or data["project_id"] != project_id:
        raise PlayableCompilationError("replay was recorded against another game")
    actions = data["actions"]
    if not isinstance(actions, list) or len(actions) > 20_000:
        raise PlayableCompilationError("invalid replay action list")
    if any(type(action) is not str or action not in ("up", "down", "left", "right")
           for action in actions):
        raise PlayableCompilationError("invalid browser action")
    if not isinstance(data["note"], str) or len(data["note"]) > 200:
        raise PlayableCompilationError("invalid browser trace note")
    return tuple(actions)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.playable_cli",
        description="Build playable original multi-level browser games without network access.",
    )
    root.add_argument("--intent", required=True, help="Exact typed original-game intent JSON")
    root.add_argument(
        "--trusted-local-operator", action="store_true",
        help="Acknowledges that operator identity and authorization were checked externally",
    )
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Generate game and verify its winning solution")
    build.add_argument("--output", required=True, help="Output self-contained .html")
    solve = commands.add_parser("solve", help="Emit a trusted winning turn-by-turn move trace")
    replay = commands.add_parser("verify-replay", help="Recompute an exported browser action trace")
    replay.add_argument("--input", required=True, help="Browser action trace JSON")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external operator authorization acknowledgement required", file=sys.stderr)
        return 2
    try:
        data = _read_json(args.intent, MAX_INPUT_BYTES)
        intent = _intent(data)
        compiled = compile_original_game(intent, authorized=True)
        if args.command == "build":
            output = Path(args.output)
            if output.suffix.lower() != ".html":
                raise PlayableCompilationError("game output requires .html extension")
            saved = export_compiled_project(compiled, output, authorized=True)
            output_data: dict[str, Any] = {
                **compiled.receipt(),
                "output": str(saved),
            }
        elif args.command == "solve":
            output_data = {
                "schema": "skeleton.game_builder.solution_trace.v1",
                "world_digest": compiled.world.digest,
                "actions": [
                    action.action for action in compiled.proof.action_receipts
                ],
                "final_state": compiled.proof.final_state.to_payload(),
                "replay_digest": compiled.proof.digest,
            }
        elif args.command == "verify-replay":
            log = _read_json(args.input, MAX_REPLAY_BYTES)
            actions = _actions(log, compiled.world.digest, compiled.world.intent.project_id)
            trace = play_actions(compiled.world, actions, authorized=True)
            output_data = {
                "schema": "skeleton.game_builder.verified_browser_replay.v1",
                "world_digest": compiled.world.digest,
                "action_count": len(actions),
                "final_state": trace.final_state.to_payload(),
                "replay_digest": trace.digest,
                "verified": True,
                "source_authenticity_verified": False,
            }
        else:
            raise PlayableCompilationError("invalid game CLI command")
    except (PlayableCompilationError, PlayableWorldError, GameplayError, OSError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(canonical_json(output_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "parser", "MAX_INPUT_BYTES", "MAX_REPLAY_BYTES"]
