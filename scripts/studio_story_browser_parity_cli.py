"""CLI for source-bound interactive story ending parity and private replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_story_browser_parity import (
    PROMPT, compile_story_browser_parity, propose_story_browser_parity,
    replay_story_browser_parity, compile_story_browser_handoff,
    publish_story_browser_parity, restore_story_browser_parity,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-leased browser quest parity")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring-file", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-preview", action="store_true")
    ap.add_argument("--playable", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and args.publish:
        ap.error("restore cannot publish")
    if args.html_preview and args.publish:
        ap.error("HTML preview cannot publish")
    try:
        docs = read_blueprint(args.project)
        options = {
            "authorized": True,
            "expected_source_digest": args.expected_source,
            "expected_initial_session_digest": args.expected_session,
        }
        if args.restore:
            receipt = restore_story_browser_parity(
                docs, args.restore, **options)
        elif args.prompt:
            proposal = propose_story_browser_parity(docs, PROMPT, **options)
            receipt = proposal["detail"]
        else:
            authoring = _private_json(args.authoring_file, 16384)
            if set(authoring) != {"actions"}:
                raise StudioQuestError("browser parity authoring requires exact actions")
            receipt = compile_story_browser_parity(
                docs, authoring["actions"], **options)
        replay_story_browser_parity(docs, receipt, authorized=True)
        output: dict[str, object] = {
            "schema": "skeleton.cli.studio_story_browser_parity.v1",
            "detail": receipt, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable or args.html_preview:
            handoff, html = compile_story_browser_handoff(
                docs, receipt, authorized=True)
            if args.html_preview:
                print(html.decode("utf-8"))
                return 0
            output["playable_handoff"] = handoff
        if args.publish:
            output["publication"] = publish_story_browser_parity(
                docs, receipt, args.publish, authorized=True)
            output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError, TypeError, KeyError) as exc:
        ap.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
