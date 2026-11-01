"""Operator CLI for source-verified playable NPC-to-dialogue previews."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_contact import (
    MAX_BYTES, compile_npc_dialogue_contact,
    publish_npc_dialogue_contact, restore_npc_dialogue_contact,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove NPC proximity and quest unlock before showing dialogue")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-walk", required=True)
    parser.add_argument("--expected-quest", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--walk-json")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--npc-id")
    parser.add_argument("--scene-id")
    parser.add_argument("--quest-actions", default="[]")
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args(argv)
    if args.restore and (args.publish or args.npc_id or args.scene_id
                         or args.quest_actions != "[]"):
        parser.error("restore cannot also compile or publish")
    if args.walk_json and (not args.npc_id or not args.scene_id):
        parser.error("walk preview requires NPC and authored scene")
    try:
        documents = read_blueprint(args.project)
        if args.restore:
            result = restore_npc_dialogue_contact(
                documents, args.restore, authorized=True,
                expected_source_digest=args.expected_source,
                expected_walk_digest=args.expected_walk,
                expected_quest_digest=args.expected_quest,
            )
        else:
            walk = _strict(args.walk_json, max_bytes=MAX_BYTES)
            actions = _strict(args.quest_actions, max_bytes=32768)
            result = compile_npc_dialogue_contact(
                documents, walk, npc_id=args.npc_id, scene_id=args.scene_id,
                quest_actions=actions, authorized=True,
                expected_source_digest=args.expected_source,
                expected_walk_digest=args.expected_walk,
                expected_quest_digest=args.expected_quest,
            )
        output: dict[str, object] = {
            "npc_dialogue": result, "file_write_performed": False,
        }
        if args.publish:
            output["publication"] = publish_npc_dialogue_contact(
                documents, result, args.publish, authorized=True,
                expected_source_digest=args.expected_source,
                expected_walk_digest=args.expected_walk,
                expected_quest_digest=args.expected_quest,
            )
            output["file_write_performed"] = True
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, KeyError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
