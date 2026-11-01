"""CLI for typed, source-replayed, read-only Jeeves world-tool batches."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_batch import (
    PROMPT, propose_world_batch_plan, compile_world_batch_plan,
    replay_world_batch_plan, execute_world_batch, replay_world_batch_execution,
    restore_world_batch_execution, publish_world_batch_execution,
    render_world_batch_html,
)
from skeleton.ai.game_builder.studio_world_batch_editor import (
    publish_world_batch_editor, load_world_batch_editor_export,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Typed read-only original world workflow")
    ap.add_argument("--expected-catalog", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--plan")
    modes.add_argument("--import-plan", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--requests")
    ap.add_argument("--baseline-plan")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-sha256", action="store_true")
    args = ap.parse_args(argv)
    if args.prompt and not args.requests:
        ap.error("prompt planning requires typed requests")
    if args.import_plan and not args.baseline_plan:
        ap.error("editor import requires baseline plan")
    try:
        if args.restore:
            if args.requests or args.baseline_plan:
                ap.error("restore cannot combine with authoring")
            detail = restore_world_batch_execution(
                args.restore, authorized=True,
                expected_catalog_digest=args.expected_catalog)
            plan = detail["plan"]
        else:
            if args.prompt:
                plan = propose_world_batch_plan(
                    PROMPT, _strict(args.requests, max_bytes=49152),
                    authorized=True, expected_catalog_digest=args.expected_catalog)
            elif args.import_plan:
                baseline = _strict(args.baseline_plan, max_bytes=49152)
                prior = replay_world_batch_plan(baseline, authorized=True)
                requests = load_world_batch_editor_export(
                    args.import_plan, authorized=True,
                    expected_catalog_digest=args.expected_catalog,
                    expected_baseline_plan_digest=prior["plan_digest"])
                plan = compile_world_batch_plan(
                    requests, authorized=True,
                    expected_catalog_digest=args.expected_catalog)
            else:
                plan = replay_world_batch_plan(
                    _strict(args.plan, max_bytes=49152), authorized=True)
                if plan["catalog_digest"] != args.expected_catalog:
                    raise StudioQuestError("stale world batch catalog lease")
            detail = execute_world_batch(plan, authorized=True)
        result: dict[str, object] = {
            "plan": plan, "execution": detail, "file_write_performed": False,
        }
        if args.html_sha256:
            result["html_sha256"] = sha256(render_world_batch_html(
                detail, authorized=True)).hexdigest()
        if args.editor_directory:
            result["editor"] = publish_world_batch_editor(
                plan, args.editor_directory, authorized=True)
        if args.publish:
            result["publication"] = publish_world_batch_execution(
                detail, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, ValueError, TypeError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
