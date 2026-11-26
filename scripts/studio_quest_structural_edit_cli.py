"""Operator structural quest edit -> recompile -> private revision publication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    publish_prompt_quest_plan, restore_prompt_quest_plan,
    render_prompt_quest_html,
)
from skeleton.ai.game_builder.studio_quest_structural_edit import (
    compile_quest_structural_edit, replay_quest_structural_edit,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Atomic source-leased quest structural editor")
    ap.add_argument("--baseline-dir", required=True, type=Path)
    ap.add_argument("--expected-baseline", required=True)
    ap.add_argument("--edits-json", required=True)
    ap.add_argument("--publish-candidate", type=Path)
    ap.add_argument("--html", action="store_true")
    args = ap.parse_args(argv)
    if args.html and args.publish_candidate:
        ap.error("read-only HTML preview cannot publish")
    try:
        baseline = restore_prompt_quest_plan(args.baseline_dir, authorized=True)
        edits = _strict(args.edits_json, max_bytes=64 * 1024)
        proof = compile_quest_structural_edit(
            baseline, edits, authorized=True,
            expected_baseline_digest=args.expected_baseline)
        replay_quest_structural_edit(
            proof, authorized=True, expected_baseline_digest=args.expected_baseline)
        candidate = proof["candidate_compilation"]
        if args.html:
            print(render_prompt_quest_html(candidate, authorized=True).decode("utf-8"))
            return 0
        output = {"proof": proof, "file_write_performed": False}
        if args.publish_candidate:
            output["publication"] = publish_prompt_quest_plan(
                candidate, args.publish_candidate, authorized=True)
            output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, PermissionError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
