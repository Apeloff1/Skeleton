"""Operator CLI for replay-verified NPC dialogue choice and private save."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_choice_commit import (
    MAX_BYTES, compile_npc_dialogue_choice_commit,
    publish_npc_dialogue_choice_commit, restore_npc_dialogue_choice_commit,
    render_npc_dialogue_choice_commit_html,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Commit one replay-verified original NPC dialogue choice")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-contact", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-walk", required=True)
    parser.add_argument("--expected-quest", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contact-json")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--alternative")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-preview", action="store_true")
    args = parser.parse_args(argv)
    if args.html_preview and args.publish:
        parser.error("read-only HTML preview cannot publish")
    if args.restore and (args.publish or args.alternative):
        parser.error("restore cannot also compile or publish")
    if args.contact_json and not args.alternative:
        parser.error("commit requires an authored alternative")
    params = {
        "authorized": True,
        "expected_contact_digest": args.expected_contact,
        "expected_source_digest": args.expected_source,
        "expected_walk_digest": args.expected_walk,
        "expected_quest_digest": args.expected_quest,
    }
    try:
        documents = read_blueprint(args.project)
        if args.restore:
            result = restore_npc_dialogue_choice_commit(
                documents, args.restore, **params)
        else:
            contact = _strict(args.contact_json, max_bytes=MAX_BYTES)
            result = compile_npc_dialogue_choice_commit(
                documents, contact, alternative=args.alternative, **params)
        output: dict[str, object] = {
            "choice_commit": result, "file_write_performed": False,
        }
        if args.publish:
            output["publication"] = publish_npc_dialogue_choice_commit(
                documents, result, args.publish, **params)
            output["file_write_performed"] = True
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, KeyError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    if args.html_preview:
        print(render_npc_dialogue_choice_commit_html(
            documents, result, **params).decode("utf-8"))
    else:
        print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
