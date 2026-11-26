"""Operator end-to-end original quest compilation -> playable ending handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_prompt_quest_plan import restore_prompt_quest_plan
from skeleton.ai.game_builder.studio_prompt_quest_playtest import (
    compile_prompt_quest_playtest, replay_prompt_quest_playtest,
)
from skeleton.ai.game_builder.studio_quest_ending_witness import (
    publish_ending_witness, render_ending_witness_html,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original quest -> playable ending proof")
    ap.add_argument("--plan-directory", required=True, type=Path)
    ap.add_argument("--expected-compilation", required=True)
    ap.add_argument("--target-ending", required=True)
    ap.add_argument("--max-states", type=int, default=512)
    ap.add_argument("--max-depth", type=int, default=16)
    ap.add_argument("--publish-witness", type=Path)
    ap.add_argument("--html-preview", action="store_true")
    args = ap.parse_args(argv)
    if args.html_preview and args.publish_witness:
        ap.error("read-only HTML preview cannot publish")
    try:
        compilation = restore_prompt_quest_plan(
            args.plan_directory, authorized=True)
        result = compile_prompt_quest_playtest(
            compilation, target_ending=args.target_ending,
            max_states=args.max_states, max_depth=args.max_depth,
            authorized=True, expected_compilation_digest=args.expected_compilation)
        replay_prompt_quest_playtest(
            result, authorized=True,
            expected_compilation_digest=args.expected_compilation)
        witness = result["ending_witness"]
        kwargs = {
            "authorized": True,
            "expected_source_digest": compilation["quest_source_digest"],
            "expected_initial_session_digest":
                compilation["initial_quest_session_digest"],
        }
        if args.html_preview:
            print(render_ending_witness_html(
                compilation["documents"], witness, **kwargs).decode("utf-8"))
            return 0
        output = {"playtest": result, "file_write_performed": False}
        if args.publish_witness:
            output["publication"] = publish_ending_witness(
                compilation["documents"], witness, args.publish_witness, **kwargs)
            output["file_write_performed"] = True
    except (StudioQuestError, OSError, PermissionError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
