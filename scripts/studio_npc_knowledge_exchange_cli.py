"""Offline CLI: source-bound NPC knowledge exchanges and private replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange import (
    PROMPT, compile_npc_knowledge_exchange, propose_npc_knowledge_exchange,
    publish_npc_knowledge_exchange, restore_npc_knowledge_exchange,
    compile_knowledge_exchange_playable,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Canonical NPC knowledge exchange")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--rendezvous")
    ap.add_argument("--knowledge")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--authoring")
    modes.add_argument("--import-authoring", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--baseline-exchange")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and (args.rendezvous or args.knowledge or args.baseline_exchange):
        ap.error("restore cannot combine with exchange authoring")
    if not args.restore and (not args.rendezvous or not args.knowledge):
        ap.error("exchange authoring requires rendezvous and knowledge receipts")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            detail = restore_npc_knowledge_exchange(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            rendezvous = _strict(args.rendezvous, max_bytes=262144)
            knowledge = _strict(args.knowledge, max_bytes=262144)
            if (type(rendezvous) is not dict or type(knowledge) is not dict
                    or rendezvous.get("source_digest") != args.expected_source
                    or knowledge.get("source_digest") != args.expected_source):
                raise StudioQuestError("stale NPC exchange source lease")
            if args.prompt:
                detail = propose_npc_knowledge_exchange(
                    docs, rendezvous, knowledge, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.import_authoring:
                    if args.baseline_exchange is None:
                        raise StudioQuestError("exchange import requires baseline receipt")
                    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange import (
                        replay_npc_knowledge_exchange,
                    )
                    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange_editor import (
                        load_npc_exchange_editor_export,
                    )
                    baseline = replay_npc_knowledge_exchange(
                        docs, _strict(args.baseline_exchange, max_bytes=393216),
                        authorized=True)
                    if (baseline["rendezvous_receipt"] != rendezvous
                            or baseline["knowledge_receipt"] != knowledge):
                        raise StudioQuestError("stale NPC exchange editor baseline")
                    authoring = load_npc_exchange_editor_export(
                        args.import_authoring, authorized=True,
                        expected_project_id=baseline["project_id"],
                        expected_source_digest=baseline["source_digest"],
                        expected_session_digest=baseline["session_digest"],
                        expected_rendezvous_digest=baseline["rendezvous_digest"],
                        expected_knowledge_digest=baseline["knowledge_digest"],
                        expected_baseline_digest=baseline["exchange_digest"])
                else:
                    if args.baseline_exchange is not None:
                        raise StudioQuestError("baseline only valid for editor import")
                    authoring = _strict(args.authoring, max_bytes=32768)
                detail = compile_npc_knowledge_exchange(
                    docs, rendezvous, knowledge, authoring, authorized=True,
                    expected_source_digest=args.expected_source)
        output = {"exchange": detail}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange_editor import (
                publish_npc_exchange_editor,
            )
            output["editor"] = publish_npc_exchange_editor(
                docs, detail, args.editor_directory, authorized=True)
        if args.playable_manifest:
            output["playable_handoff"] = compile_knowledge_exchange_playable(
                docs, detail, authorized=True)
        if args.publish:
            output["publication"] = publish_npc_knowledge_exchange(
                docs, detail, args.publish, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
