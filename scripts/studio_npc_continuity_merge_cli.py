"""Offline CLI for canonical NPC continuity branch reconciliation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_merge import (
    PROMPT, compile_npc_continuity_merge, propose_npc_continuity_merge,
    replay_npc_continuity_merge, publish_npc_continuity_merge,
    restore_npc_continuity_merge, render_npc_continuity_merge_html,
    compile_npc_continuity_merge_playable,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_merge_editor import (
    publish_npc_continuity_merge_editor, load_npc_continuity_merge_editor_export,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-replayed NPC continuity merge")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--candidate")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--decisions")
    modes.add_argument("--import-decisions", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--baseline-merge")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-sha256", action="store_true")
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore:
        if args.baseline or args.candidate or args.baseline_merge:
            ap.error("restore cannot combine with branch inputs")
    elif not args.baseline or not args.candidate:
        ap.error("reconciliation requires baseline and candidate receipts")
    if args.import_decisions and not args.baseline_merge:
        ap.error("editor import requires baseline merge receipt")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            detail = restore_npc_continuity_merge(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            baseline = _strict(args.baseline, max_bytes=524288)
            candidate = _strict(args.candidate, max_bytes=524288)
            if type(baseline) is not dict or type(candidate) is not dict:
                raise StudioQuestError("continuity branch inputs must be objects")
            if args.prompt:
                detail = propose_npc_continuity_merge(
                    docs, baseline, candidate, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.import_decisions:
                    prior = _strict(args.baseline_merge, max_bytes=786432)
                    verified = replay_npc_continuity_merge(
                        docs, prior, authorized=True)
                    if (verified["baseline_digest"] != baseline.get("journal_digest")
                            or verified["candidate_digest"] != candidate.get("journal_digest")):
                        raise StudioQuestError("stale continuity editor branch lease")
                    authoring = load_npc_continuity_merge_editor_export(
                        args.import_decisions, authorized=True,
                        expected_project_id=verified["project_id"],
                        expected_source_digest=verified["source_digest"],
                        expected_session_digest=verified["session_digest"],
                        expected_baseline_digest=verified["baseline_digest"],
                        expected_candidate_digest=verified["candidate_digest"],
                        expected_merge_digest=verified["merge_digest"])
                else:
                    authoring = _strict(args.decisions, max_bytes=16384)
                detail = compile_npc_continuity_merge(
                    docs, baseline, candidate, authoring, authorized=True,
                    expected_source_digest=args.expected_source)
        result: dict[str, object] = {"merge": detail, "file_write_performed": False}
        if args.html_sha256:
            from hashlib import sha256
            result["html_sha256"] = sha256(render_npc_continuity_merge_html(
                docs, detail, authorized=True)).hexdigest()
        if args.playable_manifest:
            result["playable_handoff"] = compile_npc_continuity_merge_playable(
                docs, detail, authorized=True)
        if args.editor_directory:
            result["editor"] = publish_npc_continuity_merge_editor(
                docs, detail, args.editor_directory, authorized=True)
        if args.publish:
            result["publication"] = publish_npc_continuity_merge(
                docs, detail, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, ValueError, TypeError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
