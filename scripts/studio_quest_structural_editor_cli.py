"""Offline quest structural editor: render, publish, or import and compile."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    restore_prompt_quest_plan, publish_prompt_quest_plan,
)
from skeleton.ai.game_builder.studio_quest_structural_editor import (
    render_quest_structural_editor, publish_quest_structural_editor,
    import_quest_structural_editor_export,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline source-bound quest structural editor")
    ap.add_argument("--baseline-dir", required=True, type=Path)
    ap.add_argument("--expected-baseline", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--render-html", action="store_true")
    modes.add_argument("--publish-editor", type=Path)
    modes.add_argument("--import-export", type=Path)
    ap.add_argument("--publish-candidate", type=Path)
    args = ap.parse_args(argv)
    if args.publish_candidate and args.import_export is None:
        ap.error("candidate publication requires a validated editor export")
    try:
        baseline = restore_prompt_quest_plan(args.baseline_dir, authorized=True)
        kw = {"authorized": True,
              "expected_baseline_digest": args.expected_baseline}
        if args.render_html:
            html, _ = render_quest_structural_editor(baseline, **kw)
            print(html.decode("utf-8"))
            return 0
        if args.publish_editor:
            output = publish_quest_structural_editor(
                baseline, args.publish_editor, **kw)
        else:
            result = import_quest_structural_editor_export(
                baseline, args.import_export, **kw)
            output = {"edit_proof": result, "file_write_performed": False}
            if args.publish_candidate:
                output["publication"] = publish_prompt_quest_plan(
                    result["candidate_compilation"], args.publish_candidate,
                    authorized=True)
                output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, PermissionError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
