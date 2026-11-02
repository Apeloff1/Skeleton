"""CLI: cross-feature source-replayed original quest playable experience."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_experience_handoff import (
    compile_quest_experience_bundle, compile_quest_experience_handoff,
    render_quest_experience_review_html, publish_quest_experience,
    restore_quest_experience,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile one source/session-bound original quest experience")
    parser.add_argument("--project", required=True)
    parser.add_argument("--localization-file", type=Path, required=True)
    parser.add_argument("--achievements-file", type=Path, required=True)
    parser.add_argument("--pacing-file", type=Path, required=True)
    parser.add_argument("--advisories-file", type=Path, required=True)
    parser.add_argument("--accept-topic", action="append", default=[])
    parser.add_argument("--handoff", action="store_true")
    parser.add_argument("--review-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.review_html and (args.handoff or args.publish or args.restore):
        parser.error("review HTML is read-only")
    if args.publish and args.restore:
        parser.error("cannot publish and restore in one operation")
    try:
        docs = read_blueprint(args.project)
        locale = read_studio_private_json(args.localization_file, 320 * 1024)
        awards = read_studio_private_json(args.achievements_file, 131072)
        pacing = read_studio_private_json(args.pacing_file, 131072)
        advisories = read_studio_private_json(args.advisories_file, 131072)
        topics = sorted(args.accept_topic)
        if args.restore:
            bundle = restore_quest_experience(
                docs, locale, awards, pacing, advisories, topics,
                args.restore, authorized=True)
        else:
            bundle = compile_quest_experience_bundle(
                docs, locale, awards, pacing, advisories, topics,
                authorized=True)
        if args.review_html:
            print(render_quest_experience_review_html(
                docs, locale, awards, pacing, advisories, topics,
                authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.studio_quest_experience.v1",
                  "experience": bundle, "file_write_performed": False,
                  "release_certified": False}
        if args.handoff:
            result["playable_handoff"] = compile_quest_experience_handoff(
                docs, locale, awards, pacing, advisories, topics,
                authorized=True)
        if args.publish:
            result["publication"] = publish_quest_experience(
                docs, locale, awards, pacing, advisories, topics,
                args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
