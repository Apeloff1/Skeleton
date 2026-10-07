"""Fixed-operation worker used by the frontier application service."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from skeleton.frontier.payloads import json_snapshot
from skeleton.services.frontier import OPERATIONS


def run_operation(operation: str, task: str, context: dict[str, Any], state_root: Path) -> dict[str, Any]:
    if not isinstance(task, str) or not task.strip() or len(task) > 20_000:
        raise ValueError("task must contain 1 to 20000 characters")
    if operation == "gameforge.npc":
        from skeleton.pipelines.npc import NpcPipeline

        if set(context) - {"name", "dialogue_beats", "archetype"}:
            raise ValueError("unsupported NPC options")
        beats = context.get("dialogue_beats", 3)
        if isinstance(beats, bool) or not isinstance(beats, int) or not 1 <= beats <= 12:
            raise ValueError("dialogue_beats must be an integer between 1 and 12")
        for key in ("name", "archetype"):
            if key in context and (not isinstance(context[key], str) or not context[key].strip()):
                raise ValueError(f"{key} must be a non-empty string")
        params = {"archetype": context["archetype"]} if "archetype" in context else {}
        return (
            NpcPipeline(root=state_root)
            .run(task, name=context.get("name"), dialogue_beats=beats, params=params)
            .to_dict()
        )
    if operation == "gameforge.logic":
        from skeleton.pipelines.game_logic import GameLogicPipeline

        if set(context) - {"title", "max_level", "curve", "currency"}:
            raise ValueError("unsupported game-logic options")
        level = context.get("max_level", 50)
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 1000:
            raise ValueError("max_level must be an integer between 1 and 1000")
        for key in ("title", "curve", "currency"):
            if key in context and (not isinstance(context[key], str) or not context[key].strip()):
                raise ValueError(f"{key} must be a non-empty string")
        return GameLogicPipeline(root=state_root).run(task, **context).to_dict()
    if operation == "jeeves.review":
        from skeleton.school.code_intelligence import CodeIntelligenceEngine

        if set(context) - {"language"}:
            raise ValueError("unsupported review options")
        language = context.get("language", "python")
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string")
        return asdict(CodeIntelligenceEngine().analyze(task, language=language))
    raise ValueError("unknown pipeline operation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=tuple(OPERATIONS))
    parser.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("request exceeds worker byte budget")
        payload = json_snapshot(json.loads(raw))
        if not isinstance(payload, dict) or not isinstance(payload.get("context", {}), dict):
            raise ValueError("invalid worker request")
        with contextlib.redirect_stdout(sys.stderr):
            output = run_operation(
                args.operation, payload.get("task"), payload.get("context", {}), args.state_root
            )
        encoded = json.dumps(output, allow_nan=False).encode("utf-8")
        if len(encoded) > 1_048_576:
            raise ValueError("result exceeds worker byte budget")
        sys.stdout.buffer.write(encoded)
        return 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
