"""CLI for exact-session NPC, dialogue and quest experience assembly."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_character_experience import (
    compile_quest_character_experience, compile_quest_character_experience_handoff,
    render_quest_character_walkthrough_html, publish_quest_character_experience,
    restore_quest_character_experience,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose original quest character experience")
    parser.add_argument("--project", required=True)
    for field in ("branch", "npc", "dialogue", "localization", "achievements",
                  "pacing", "advisories"):
        parser.add_argument("--" + field + "-file", type=Path, required=True)
    parser.add_argument("--accept-topic", action="append", default=[])
    parser.add_argument("--handoff", action="store_true")
    parser.add_argument("--walkthrough-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.walkthrough_html and (args.handoff or args.publish or args.restore):
        parser.error("walkthrough HTML is read-only")
    if args.publish and args.restore:
        parser.error("cannot publish and restore together")
    try:
        docs = read_blueprint(args.project)
        inputs = [
            read_studio_private_json(getattr(args, field + "_file"), 393216)
            for field in ("branch", "npc", "dialogue", "localization",
                          "achievements", "pacing", "advisories")
        ]
        topics = sorted(args.accept_topic)
        parts = (docs, *inputs, topics)
        if args.restore:
            checked = restore_quest_character_experience(
                *parts, args.restore, authorized=True)
        else:
            checked = compile_quest_character_experience(*parts, authorized=True)
        if args.walkthrough_html:
            print(render_quest_character_walkthrough_html(
                *parts, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.studio_quest_character_experience.v1",
                  "character_experience": checked,
                  "file_write_performed": False, "release_certified": False}
        if args.handoff:
            result["playable_handoff"] = compile_quest_character_experience_handoff(
                *parts, authorized=True)
        if args.publish:
            result["publication"] = publish_quest_character_experience(
                *parts, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
