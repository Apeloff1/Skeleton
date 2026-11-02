"""Operator CLI for original source-bound quest causal witness proofs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_consequence_diff import (
    PROMPT, compile_quest_consequence_diff, propose_quest_consequence_diff,
)
from skeleton.ai.game_builder.studio_quest_causal_trace import (
    compile_quest_causal_trace, replay_quest_causal_trace,
    compile_quest_causal_handoff, render_quest_causal_html,
    publish_quest_causal_trace, restore_quest_causal_trace,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Canonical authored quest ending predicate witnesses")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring-file", type=Path)
    modes.add_argument("--restore", type=Path)
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-preview", action="store_true")
    parser.add_argument("--playable", action="store_true")
    args = parser.parse_args(argv)
    if args.restore and args.publish:
        parser.error("restore cannot publish")
    if args.html_preview and (args.publish or args.playable):
        parser.error("HTML preview cannot publish or hand off")
    try:
        docs = read_blueprint(args.project)
        options = {
            "authorized": True, "expected_source_digest": args.expected_source,
            "expected_initial_session_digest": args.expected_session,
        }
        if args.restore:
            trace = restore_quest_causal_trace(
                docs, None, args.restore, authorized=True)
            if (trace["source_digest"] != args.expected_source
                    or trace["initial_session_digest"] != args.expected_session):
                raise StudioQuestError("stale causal restore source/session")
            authoring = {
                "baseline_actions": trace["baseline"]["actions"],
                "candidate_actions": trace["candidate"]["actions"],
            }
            consequence = compile_quest_consequence_diff(
                docs, authoring, **options)
        else:
            if args.prompt:
                consequence = propose_quest_consequence_diff(
                    docs, PROMPT, **options)
            else:
                authoring = _private_json(args.authoring_file, 32768)
                consequence = compile_quest_consequence_diff(
                    docs, authoring, **options)
            trace = compile_quest_causal_trace(
                docs, consequence, authorized=True)
        replay_quest_causal_trace(docs, consequence, trace, authorized=True)
        if args.html_preview:
            print(render_quest_causal_html(
                docs, consequence, trace, authorized=True).decode("utf-8"))
            return 0
        output: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_causal_trace.v1",
            "trace": trace, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            output["playable_handoff"] = compile_quest_causal_handoff(
                docs, consequence, trace, authorized=True)
        if args.publish:
            output["publication"] = publish_quest_causal_trace(
                docs, consequence, trace, args.publish, authorized=True)
            output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
