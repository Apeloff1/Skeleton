"""CLI for original quest content advisories, consent, custody and handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_advisories import (
    compile_quest_advisories, compile_advisory_handoff,
    evaluate_player_advisories, publish_quest_advisories,
    restore_quest_advisories, render_advisory_editor_html,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Author and review source-bound quest content advisories")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--editor-html", action="store_true")
    parser.add_argument("--handoff", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--check-consent", action="store_true")
    parser.add_argument("--accept-topic", action="append", default=[])
    args = parser.parse_args(argv)
    if (args.plan_file is None) == (args.restore is None):
        parser.error("supply exactly one of --plan-file or --restore")
    if args.restore is not None and (args.editor_html or args.publish):
        parser.error("restore cannot publish or edit")
    if args.editor_html and (args.publish or args.handoff or args.check_consent):
        parser.error("editor is preview only")
    if args.accept_topic and not args.check_consent:
        parser.error("--accept-topic requires --check-consent")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            receipt = restore_quest_advisories(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if receipt["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale advisory initial session")
        else:
            receipt = compile_quest_advisories(
                docs, read_studio_private_json(args.plan_file, 65536),
                authorized=True, expected_source_digest=args.expected_source,
                expected_initial_session_digest=args.expected_session)
        if args.editor_html:
            print(render_advisory_editor_html(
                docs, receipt, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.studio_quest_advisories.v1",
                  "advisories": receipt, "file_write_performed": False,
                  "release_certified": False}
        if args.handoff:
            result["playable_handoff"] = compile_advisory_handoff(
                docs, receipt, authorized=True)
        if args.check_consent:
            result["player_consent"] = evaluate_player_advisories(
                docs, receipt, sorted(args.accept_topic), authorized=True)
        if args.publish is not None:
            result["publication"] = publish_quest_advisories(
                docs, receipt, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
