"""Offline CLI for authored NPC rendezvous, private replay and handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous import (
    PROMPT, compile_npc_rendezvous, propose_npc_rendezvous,
    restore_npc_rendezvous, publish_npc_rendezvous, compile_rendezvous_playable,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound NPC rendezvous compiler")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--transit")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--meetings")
    modes.add_argument("--import-meetings", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--baseline-rendezvous")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and (args.transit or args.baseline_rendezvous):
        ap.error("restore cannot be combined with authoring receipts")
    if not args.restore and not args.transit:
        ap.error("authoring requires transit receipt")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            result = restore_npc_rendezvous(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            transit = _strict(args.transit, max_bytes=262144)
            if type(transit) is not dict or transit.get("source_digest") != args.expected_source:
                raise StudioQuestError("stale NPC rendezvous transit lease")
            if args.prompt:
                result = propose_npc_rendezvous(
                    docs, transit, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.import_meetings:
                    if args.baseline_rendezvous is None:
                        raise StudioQuestError("rendezvous import requires original receipt")
                    from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous import (
                        replay_npc_rendezvous,
                    )
                    from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous_editor import (
                        load_npc_rendezvous_editor_export,
                    )
                    original = replay_npc_rendezvous(
                        docs, _strict(args.baseline_rendezvous, max_bytes=262144),
                        authorized=True)
                    if original["transit_receipt"] != transit:
                        raise StudioQuestError("stale NPC rendezvous editor transit")
                    meetings = load_npc_rendezvous_editor_export(
                        args.import_meetings, authorized=True,
                        expected_project_id=original["project_id"],
                        expected_source_digest=original["source_digest"],
                        expected_session_digest=original["session_digest"],
                        expected_transit_digest=original["transit_digest"],
                        expected_baseline_digest=original["rendezvous_digest"])
                else:
                    if args.baseline_rendezvous is not None:
                        raise StudioQuestError("baseline only valid for editor import")
                    meetings = _strict(args.meetings, max_bytes=32768)
                result = compile_npc_rendezvous(
                    docs, transit, meetings, authorized=True,
                    expected_source_digest=args.expected_source)
        output = {"rendezvous": result}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous_editor import (
                publish_npc_rendezvous_editor,
            )
            output["editor"] = publish_npc_rendezvous_editor(
                docs, result, args.editor_directory, authorized=True)
        if args.playable_manifest:
            output["playable_handoff"] = compile_rendezvous_playable(
                docs, result, authorized=True)
        if args.publish:
            output["publication"] = publish_npc_rendezvous(
                docs, result, args.publish, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
