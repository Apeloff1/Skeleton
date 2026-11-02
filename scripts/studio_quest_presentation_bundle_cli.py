"""Read-only, exact-source quest presentation handoff CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_presentation_bundle import (
    compile_quest_presentation_bundle, compile_quest_presentation_handoff,
    render_quest_presentation_preview_html,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble canonical quest presentation")
    parser.add_argument("--project", required=True)
    parser.add_argument("--localization-file", required=True, type=Path)
    parser.add_argument("--achievements-file", required=True, type=Path)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    parser.add_argument("--preview-html", action="store_true")
    parser.add_argument("--handoff", action="store_true")
    args = parser.parse_args(argv)
    if args.preview_html and args.handoff:
        parser.error("preview is read-only and cannot request handoff")
    try:
        docs = read_blueprint(args.project)
        locale = read_studio_private_json(args.localization_file, 320 * 1024)
        awards = read_studio_private_json(args.achievements_file, 131072)
        if (locale.get("source_digest") != args.expected_source
                or awards.get("source_digest") != args.expected_source
                or locale.get("initial_session_digest") != args.expected_session
                or awards.get("initial_session_digest") != args.expected_session):
            raise StudioQuestError("stale quest presentation CLI source/session lease")
        if args.preview_html:
            print(render_quest_presentation_preview_html(
                docs, locale, awards, authorized=True).decode("utf-8"))
            return 0
        bundle = compile_quest_presentation_bundle(
            docs, locale, awards, authorized=True)
        result = {"schema": "skeleton.cli.studio_quest_presentation_bundle.v1",
                  "bundle": bundle, "file_write_performed": False,
                  "release_certified": False}
        if args.handoff:
            result["playable_handoff"] = compile_quest_presentation_handoff(
                docs, locale, awards, authorized=True)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
