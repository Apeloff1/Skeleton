"""Operator CLI for original source-leased quest counterfactuals."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_consequence_diff import (
    PROMPT, compile_quest_consequence_diff, propose_quest_consequence_diff,
    replay_quest_consequence_diff, compile_quest_consequence_handoff,
    render_quest_consequence_html, publish_quest_consequence_diff,
    restore_quest_consequence_diff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical authored quest choice comparison")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring-file", type=Path)
    modes.add_argument("--restore", type=Path)
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--playable", action="store_true")
    parser.add_argument("--html-preview", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and args.publish:
        parser.error("restore cannot publish")
    if args.html_preview and (args.publish or args.playable):
        parser.error("HTML preview cannot publish or hand off")
    try:
        docs = read_blueprint(args.project)
        options = {"authorized": True, "expected_source_digest": args.expected_source,
                   "expected_initial_session_digest": args.expected_session}
        if args.restore:
            report = restore_quest_consequence_diff(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if report["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored consequence session")
        elif args.prompt:
            report = propose_quest_consequence_diff(docs, PROMPT, **options)
        else:
            report = compile_quest_consequence_diff(
                docs, _private_json(args.authoring_file, 32768), **options)
        replay_quest_consequence_diff(docs, report, authorized=True)
        if args.html_preview:
            print(render_quest_consequence_html(
                docs, report, authorized=True).decode("utf-8"))
            return 0
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_consequence_diff.v1",
            "consequences": report, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            result["playable_handoff"] = compile_quest_consequence_handoff(
                docs, report, authorized=True)
        if args.publish:
            result["publication"] = publish_quest_consequence_diff(
                docs, report, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
