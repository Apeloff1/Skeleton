"""Offline CLI for source-bound NPC continuity timeline and annotations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_journal import (
    PROMPT, compile_npc_continuity_journal, propose_npc_continuity_journal,
    publish_npc_continuity_journal, restore_npc_continuity_journal,
    render_npc_continuity_html, compile_continuity_playable,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Canonical NPC continuity timeline")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--exchange")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring")
    modes.add_argument("--import-authoring", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--baseline-journal")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--html-sha256", action="store_true")
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and (args.exchange or args.baseline_journal):
        ap.error("restore cannot combine with continuity authoring")
    if not args.restore and not args.exchange:
        ap.error("continuity authoring requires exchange receipt")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            detail = restore_npc_continuity_journal(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            exchange = _strict(args.exchange, max_bytes=393216)
            if type(exchange) is not dict or exchange.get("source_digest") != args.expected_source:
                raise StudioQuestError("stale NPC continuity exchange lease")
            if args.prompt:
                detail = propose_npc_continuity_journal(
                    docs, exchange, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.import_authoring:
                    if args.baseline_journal is None:
                        raise StudioQuestError("continuity import requires baseline")
                    from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_journal import (
                        replay_npc_continuity_journal,
                    )
                    from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_editor import (
                        load_npc_continuity_editor_export,
                    )
                    baseline = replay_npc_continuity_journal(
                        docs, _strict(args.baseline_journal, max_bytes=524288),
                        authorized=True)
                    if baseline["exchange_receipt"] != exchange:
                        raise StudioQuestError("stale NPC continuity editor exchange")
                    authoring = load_npc_continuity_editor_export(
                        args.import_authoring, authorized=True,
                        expected_project_id=baseline["project_id"],
                        expected_source_digest=baseline["source_digest"],
                        expected_session_digest=baseline["session_digest"],
                        expected_exchange_digest=baseline["exchange_digest"],
                        expected_baseline_digest=baseline["journal_digest"])
                else:
                    if args.baseline_journal is not None:
                        raise StudioQuestError("baseline only valid for editor import")
                    authoring = _strict(args.authoring, max_bytes=32768)
                detail = compile_npc_continuity_journal(
                    docs, exchange, authoring, authorized=True,
                    expected_source_digest=args.expected_source)
        output = {"journal": detail}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_editor import (
                publish_npc_continuity_editor,
            )
            output["editor"] = publish_npc_continuity_editor(
                docs, detail, args.editor_directory, authorized=True)
        if args.html_sha256:
            from hashlib import sha256
            html = render_npc_continuity_html(
                docs, detail, authorized=True)
            output["html_sha256"] = sha256(html).hexdigest()
            output["html_bytes"] = len(html)
        if args.playable_manifest:
            output["playable_handoff"] = compile_continuity_playable(
                docs, detail, authorized=True)
        if args.publish:
            output["publication"] = publish_npc_continuity_journal(
                docs, detail, args.publish, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
