"""Compare original quest revisions and verify ending coverage before release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_prompt_quest_plan import restore_prompt_quest_plan
from skeleton.ai.game_builder.studio_quest_regression_matrix import (
    compile_quest_regression_matrix, replay_quest_regression_matrix,
    render_quest_regression_html, publish_quest_regression_matrix,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-verified quest ending regression review")
    ap.add_argument("--baseline-dir", required=True, type=Path)
    ap.add_argument("--candidate-dir", required=True, type=Path)
    ap.add_argument("--expected-baseline", required=True)
    ap.add_argument("--expected-candidate", required=True)
    ap.add_argument("--max-states", type=int, default=256)
    ap.add_argument("--max-depth", type=int, default=16)
    ap.add_argument("--publish-dir", type=Path)
    ap.add_argument("--html", action="store_true")
    args = ap.parse_args(argv)
    if args.html and args.publish_dir:
        ap.error("HTML preview is read-only and cannot publish")
    try:
        before = restore_prompt_quest_plan(args.baseline_dir, authorized=True)
        after = restore_prompt_quest_plan(args.candidate_dir, authorized=True)
        kw = {
            "authorized": True,
            "expected_baseline_digest": args.expected_baseline,
            "expected_candidate_digest": args.expected_candidate,
        }
        result = compile_quest_regression_matrix(
            before, after, max_states=args.max_states, max_depth=args.max_depth, **kw)
        replay_quest_regression_matrix(result, **kw)
        if args.html:
            print(render_quest_regression_html(result, **kw).decode("utf-8"))
            return 0
        output = {"matrix": result, "file_write_performed": False}
        if args.publish_dir:
            output["publication"] = publish_quest_regression_matrix(
                result, args.publish_dir, **kw)
            output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, PermissionError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
