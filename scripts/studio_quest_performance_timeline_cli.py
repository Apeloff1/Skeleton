"""CLI for source-replayed original dialogue performance timing budgets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json
from skeleton.ai.game_builder.studio_quest_performance_timeline import (
    PROMPT, propose_performance_timeline, compile_performance_timeline,
    publish_performance_timeline, restore_performance_timeline,
    render_performance_timeline_html, render_performance_timeline_editor,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile original quest performance timing")
    parser.add_argument("--project", required=True)
    for field in ("branch", "npc", "dialogue", "dialogue-locale",
                  "localization", "achievements", "pacing", "advisories"):
        parser.add_argument("--" + field + "-file", type=Path, required=True)
    parser.add_argument("--accept-topic", action="append", default=[])
    parser.add_argument("--voice-file", type=Path, required=True)
    parser.add_argument("--chronology-file", type=Path, required=True)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--preview-html", action="store_true")
    parser.add_argument("--editor-html", action="store_true")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.publish and args.restore:
        parser.error("cannot publish and restore together")
    if args.editor_html and (args.publish or args.restore or args.preview_html):
        parser.error("editor is read-only")
    if args.preview_html and (args.publish or args.restore):
        parser.error("preview is read-only")
    try:
        documents = read_blueprint(args.project)
        fields = ("branch", "npc", "dialogue", "dialogue_locale",
                  "localization", "achievements", "pacing", "advisories")
        parts = tuple(read_studio_private_json(
            getattr(args, f + "_file"), 384 * 1024) for f in fields)
        parts += (sorted(args.accept_topic),)
        voice = read_studio_private_json(args.voice_file, 384 * 1024)
        chronology = read_studio_private_json(args.chronology_file, 256 * 1024)
        kwargs = {"voice_receipt": voice, "chronology_receipt": chronology}
        if args.restore:
            receipt = restore_performance_timeline(
                documents, *parts, directory=args.restore,
                authorized=True, **kwargs)
        else:
            if args.plan_file:
                plan = read_studio_private_json(args.plan_file, 128 * 1024)
            else:
                plan = propose_performance_timeline(
                    documents, *parts, prompt=PROMPT,
                    expected_voice_digest=voice["voice_direction_digest"],
                    expected_chronology_digest=chronology["chronology_digest"],
                    authorized=True, **kwargs)
            if args.editor_html:
                print(render_performance_timeline_editor(
                    documents, *parts, plan=plan, authorized=True,
                    **kwargs).decode("utf-8"))
                return 0
            if not args.plan_file:
                if args.publish or args.preview_html:
                    parser.error("reviewed --plan-file required")
                print(json.dumps({"schema": "skeleton.cli.quest_performance_plan.v1",
                                  "plan": plan}, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False))
                return 0
            receipt = compile_performance_timeline(
                documents, *parts, plan=plan,
                expected_voice_digest=voice["voice_direction_digest"],
                expected_chronology_digest=chronology["chronology_digest"],
                authorized=True, **kwargs)
        if args.preview_html:
            print(render_performance_timeline_html(
                documents, *parts, receipt=receipt,
                authorized=True, **kwargs).decode("utf-8"))
            return 0
        result = {"schema": "skeleton.cli.quest_performance_timeline.v1",
                  "performance_timeline": receipt, "file_write_performed": False}
        if args.publish:
            result["publication"] = publish_performance_timeline(
                documents, *parts, receipt=receipt,
                directory=args.publish, authorized=True, **kwargs)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError, KeyError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
