"""CLI for locale-consistent NPC dialogue and character experience handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_character_locale import (
    compile_quest_character_locale_handoff,
    render_quest_character_locale_html,
    publish_quest_character_locale, restore_quest_character_locale,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile original localized character handoff")
    parser.add_argument("--project", required=True)
    for field in ("branch", "npc", "dialogue", "dialogue-locale",
                  "localization", "achievements", "pacing", "advisories"):
        parser.add_argument("--" + field + "-file", type=Path, required=True)
    parser.add_argument("--accept-topic", action="append", default=[])
    parser.add_argument("--review-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.review_html and (args.publish or args.restore):
        parser.error("HTML review is read-only")
    if args.publish and args.restore:
        parser.error("cannot publish and restore together")
    try:
        docs = read_blueprint(args.project)
        fields = ("branch", "npc", "dialogue", "dialogue_locale",
                  "localization", "achievements", "pacing", "advisories")
        inputs = [read_studio_private_json(getattr(args, f + "_file"), 524288)
                  for f in fields]
        parts = (docs, *inputs, sorted(args.accept_topic))
        if args.restore:
            checked = restore_quest_character_locale(
                *parts, args.restore, authorized=True)
        else:
            checked = compile_quest_character_locale_handoff(
                *parts, authorized=True)
        if args.review_html:
            print(render_quest_character_locale_html(
                *parts, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.studio_quest_character_locale.v1",
                  "playable_handoff": checked, "file_write_performed": False,
                  "release_certified": False}
        if args.publish:
            result["publication"] = publish_quest_character_locale(
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
