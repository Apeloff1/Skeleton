"""Operator CLI for canonical original quest voice-direction proposals and replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_character_locale import (
    compile_quest_character_locale_handoff,
)
from skeleton.ai.game_builder.studio_quest_voice_direction import (
    PROMPT, propose_voice_direction, compile_voice_direction,
    render_voice_direction_editor, render_voice_direction_preview,
    publish_voice_direction, restore_voice_direction,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review original quest performance cues")
    parser.add_argument("--project", required=True)
    for field in ("branch", "npc", "dialogue", "dialogue-locale",
                  "localization", "achievements", "pacing", "advisories"):
        parser.add_argument("--" + field + "-file", type=Path, required=True)
    parser.add_argument("--accept-topic", action="append", default=[])
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--editor-html", action="store_true")
    parser.add_argument("--preview-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.publish and args.restore:
        parser.error("cannot publish and restore together")
    if args.editor_html and (args.preview_html or args.publish or args.restore):
        parser.error("voice editor export is a read-only operation")
    if args.preview_html and (args.publish or args.restore):
        parser.error("voice preview is a read-only operation")
    try:
        docs = read_blueprint(args.project)
        fields = ("branch", "npc", "dialogue", "dialogue_locale",
                  "localization", "achievements", "pacing", "advisories")
        parts = tuple(read_studio_private_json(
            getattr(args, field + "_file"), 384 * 1024) for field in fields)
        parts += (sorted(args.accept_topic),)
        base = compile_quest_character_locale_handoff(docs, *parts, authorized=True)
        if args.restore:
            checked = restore_voice_direction(
                docs, *parts, directory=args.restore, authorized=True)
        else:
            if args.plan_file:
                plan = read_studio_private_json(args.plan_file, 256 * 1024)
            else:
                plan = propose_voice_direction(
                    docs, *parts, prompt=PROMPT,
                    expected_handoff_digest=base["handoff_digest"], authorized=True)
            if args.editor_html:
                print(render_voice_direction_editor(
                    docs, *parts, plan=plan, authorized=True).decode("utf-8"))
                return 0
            if not args.plan_file:
                if args.publish or args.preview_html:
                    parser.error("reviewed --plan-file required for compile or publication")
                print(json.dumps({"schema": "skeleton.cli.quest_voice_proposal.v1",
                                  "plan": plan}, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False))
                return 0
            checked = compile_voice_direction(
                docs, *parts, plan=plan,
                expected_handoff_digest=base["handoff_digest"], authorized=True)
        if args.preview_html:
            print(render_voice_direction_preview(
                docs, *parts, receipt=checked, authorized=True).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.quest_voice_direction.v1",
                  "voice_direction": checked, "file_write_performed": False}
        if args.publish:
            result["publication"] = publish_voice_direction(
                docs, *parts, receipt=checked, directory=args.publish,
                authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
