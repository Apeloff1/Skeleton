"""Offline source-replayed quest hint authoring, compilation and custody."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_quest_hint_deck import (
    PROMPT, compile_quest_hint_deck, propose_quest_hint_deck,
    replay_quest_hint_deck, publish_quest_hint_deck, restore_quest_hint_deck,
    render_quest_hint_html, compile_quest_hint_playable,
)
from skeleton.ai.game_builder.studio_quest_hint_editor import (
    publish_quest_hint_editor, load_quest_hint_editor_export,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-leased quest accessibility hints")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--actions")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring")
    modes.add_argument("--import-authoring", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--baseline-deck")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-sha256", action="store_true")
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and (args.actions or args.baseline_deck):
        ap.error("restore cannot combine with hint authoring")
    if not args.restore and args.actions is None:
        ap.error("quest hint authoring requires replay actions")
    if args.import_authoring and not args.baseline_deck:
        ap.error("editor import requires baseline hint deck")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            detail = restore_quest_hint_deck(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            actions = _strict(args.actions, max_bytes=16384)
            if args.prompt:
                detail = propose_quest_hint_deck(
                    docs, actions, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.import_authoring:
                    prior = replay_quest_hint_deck(
                        docs, _strict(args.baseline_deck, max_bytes=262144),
                        authorized=True)
                    if replay_quest(docs, actions, authorized=True).digest != prior["session_digest"]:
                        raise StudioQuestError("stale quest hint editor session lease")
                    authoring = load_quest_hint_editor_export(
                        args.import_authoring, authorized=True,
                        expected_project_id=prior["project_id"],
                        expected_source_digest=prior["source_digest"],
                        expected_session_digest=prior["session_digest"],
                        expected_baseline_digest=prior["hint_deck_digest"])
                else:
                    authoring = _strict(args.authoring, max_bytes=32768)
                detail = compile_quest_hint_deck(
                    docs, actions, authoring, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=prior["session_digest"]
                    if args.import_authoring else None)
        result: dict[str, object] = {"hint_deck": detail, "file_write_performed": False}
        if args.html_sha256:
            from hashlib import sha256
            result["html_sha256"] = sha256(render_quest_hint_html(
                docs, detail, authorized=True)).hexdigest()
        if args.playable_manifest:
            result["playable_handoff"] = compile_quest_hint_playable(
                docs, detail, authorized=True)
        if args.editor_directory:
            result["editor"] = publish_quest_hint_editor(
                docs, detail, args.editor_directory, authorized=True)
        if args.publish:
            result["publication"] = publish_quest_hint_deck(
                docs, detail, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (StudioQuestError, OSError, ValueError, TypeError) as exc:
        ap.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
