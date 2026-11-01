"""CLI original quest authoring, CAS revision and private replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    compile_prompt_quest_plan, revise_prompt_quest_plan,
    restore_prompt_quest_plan, publish_prompt_quest_plan,
    render_prompt_quest_html,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original typed quest authoring")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan-json")
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--expected-plan")
    ap.add_argument("--edit-json")
    ap.add_argument("--expected-receipt")
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-preview", action="store_true")
    args = ap.parse_args(argv)
    if args.plan_json and args.edit_json:
        ap.error("edit requires a persisted original quest receipt")
    if bool(args.edit_json) != bool(args.expected_receipt):
        ap.error("edit requires an exact receipt CAS digest")
    if args.publish and args.html_preview:
        ap.error("read-only HTML preview cannot publish")
    try:
        if args.restore:
            result = restore_prompt_quest_plan(args.restore, authorized=True)
            if args.edit_json:
                edit = _strict(args.edit_json, max_bytes=16384)
                result = revise_prompt_quest_plan(
                    result, edit, authorized=True,
                    expected_receipt_digest=args.expected_receipt)
        else:
            plan = _strict(args.plan_json, max_bytes=64 * 1024)
            digest = _digest(plan)
            if args.expected_plan and args.expected_plan != digest:
                raise StudioQuestError("stale typed original quest plan")
            result = compile_prompt_quest_plan(
                plan, authorized=True, expected_plan_digest=digest)
        if args.html_preview:
            print(render_prompt_quest_html(result, authorized=True).decode("utf-8"))
            return 0
        output = {"compilation": result, "file_write_performed": False}
        if args.publish:
            output["publication"] = publish_prompt_quest_plan(
                result, args.publish, authorized=True)
            output["file_write_performed"] = True
    except (StudioQuestError, OSError, PermissionError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
