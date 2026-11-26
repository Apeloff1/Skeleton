"""Operator CLI for authored quest predicate provenance and reviewed handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_cause_editor import render_quest_cause_editor
from skeleton.ai.game_builder.studio_quest_cause_trace import (
    PROMPT, propose_quest_cause_trace, compile_quest_cause_trace,
    render_quest_cause_html, publish_quest_cause_trace,
    restore_quest_cause_trace, compile_quest_cause_handoff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain source-replayed quest ending causes")
    parser.add_argument("--project", required=True)
    parser.add_argument("--actions-file", type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--editor-html", action="store_true")
    parser.add_argument("--handoff", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and (args.actions_file or args.plan_file or args.publish):
        parser.error("--restore is exclusive with authoring and publication")
    if args.publish and (args.html or args.editor_html):
        parser.error("HTML output is a read-only preview")
    if args.editor_html and (args.restore or args.handoff or args.html):
        parser.error("editor requires a source-bound authoring plan")
    if args.publish and args.handoff:
        parser.error("publish and handoff are separate reviewed operations")
    try:
        documents = read_blueprint(args.project)
        program = compile_quest_program(documents)
        initial = start_quest(documents, authorized=True)
        if args.restore:
            receipt = restore_quest_cause_trace(
                documents, args.restore, authorized=True,
                expected_source_digest=program.source_digest)
        else:
            if args.plan_file:
                plan = read_studio_private_json(args.plan_file, 48 * 1024)
            else:
                if not args.actions_file:
                    parser.error("--actions-file required for a new causal proposal")
                actions = read_studio_private_json(
                    args.actions_file, 48 * 1024).get("actions")
                plan = propose_quest_cause_trace(
                    documents, PROMPT, actions, authorized=True,
                    expected_source_digest=program.source_digest,
                    expected_initial_session_digest=initial.digest)
                if args.editor_html:
                    print(render_quest_cause_editor(
                        documents, plan, authorized=True).decode("utf-8"))
                    return 0
                if args.publish or args.html or args.handoff:
                    parser.error("reviewed --plan-file required before compilation")
                print(json.dumps({"schema": "skeleton.cli.quest_cause_proposal.v1",
                                  "plan": plan}, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False))
                return 0
            if args.editor_html:
                print(render_quest_cause_editor(
                    documents, plan, authorized=True).decode("utf-8"))
                return 0
            receipt = compile_quest_cause_trace(
                documents, plan, authorized=True,
                expected_source_digest=program.source_digest,
                expected_initial_session_digest=initial.digest)
        if args.html:
            print(render_quest_cause_html(
                documents, receipt, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.quest_cause_trace.v1",
                  "trace": receipt, "file_write_performed": False}
        if args.handoff:
            result["handoff"] = compile_quest_cause_handoff(
                documents, receipt, authorized=True)
        if args.publish:
            result["publication"] = publish_quest_cause_trace(
                documents, receipt, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
