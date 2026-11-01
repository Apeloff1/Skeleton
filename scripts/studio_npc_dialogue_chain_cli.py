"""Operator CLI: multi-scene NPC dialogue chain with private persistence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_chain import (
    MAX_BYTES, compile_npc_dialogue_chain, publish_npc_dialogue_chain,
    render_npc_dialogue_chain_html, restore_npc_dialogue_chain,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay-verified NPC dialogue chain")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-walk", required=True)
    parser.add_argument("--expected-quest", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--walk-json")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--steps-json")
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-preview", action="store_true")
    args = parser.parse_args(argv)
    if args.html_preview and args.publish:
        parser.error("read-only HTML preview cannot publish")
    if args.restore and (args.steps_json is not None or args.publish):
        parser.error("restore cannot compile or publish")
    if args.walk_json is not None and args.steps_json is None:
        parser.error("compile requires authored --steps-json")
    params = {
        "authorized": True,
        "expected_source_digest": args.expected_source,
        "expected_walk_digest": args.expected_walk,
        "expected_quest_digest": args.expected_quest,
    }
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            result = restore_npc_dialogue_chain(docs, args.restore, **params)
        else:
            walk = _strict(args.walk_json, max_bytes=MAX_BYTES)
            steps = _strict(args.steps_json, max_bytes=MAX_BYTES)
            actions = _strict(args.actions_json, max_bytes=16384)
            result = compile_npc_dialogue_chain(
                docs, walk, initial_quest_actions=actions,
                steps=steps, **params)
        if args.html_preview:
            print(render_npc_dialogue_chain_html(
                docs, result, **params).decode("utf-8"))
            return 0
        output: dict[str, Any] = {
            "chain": result, "file_write_performed": False,
        }
        if args.publish:
            output["publication"] = publish_npc_dialogue_chain(
                docs, result, args.publish, **params)
            output["file_write_performed"] = True
    except (StudioQuestError, PermissionError, OSError, ValueError, TypeError,
            KeyError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
