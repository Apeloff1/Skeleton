"""Source-bound NPC transit planner CLI with private custody and playable gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_npc_transit import (
    PROMPT, compile_npc_transit, propose_npc_transit,
    publish_npc_transit, restore_npc_transit, compile_transit_playable,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-leased NPC transit proof")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--temporal-receipt")
    ap.add_argument("--prompt", action="store_true")
    ap.add_argument("--graph")
    ap.add_argument("--import-graph", type=Path)
    ap.add_argument("--baseline-transit")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore is not None:
        if (args.prompt or args.graph is not None or args.temporal_receipt is not None
                or args.import_graph is not None or args.baseline_transit is not None):
            ap.error("restore cannot be combined with transit authoring")
    elif args.temporal_receipt is None or (sum((args.prompt, args.graph is not None,
             args.import_graph is not None)) != 1):
        ap.error("supply temporal receipt and exactly one prompt or graph")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            result = restore_npc_transit(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            temporal = _strict(args.temporal_receipt, max_bytes=262144)
            if type(temporal) is not dict or temporal.get("source_digest") != args.expected_source:
                raise StudioQuestError("NPC transit source lease mismatch")
            if args.prompt:
                result = propose_npc_transit(
                    docs, temporal, PROMPT, authorized=True)
            else:
                if args.import_graph is not None:
                    from skeleton.ai.game_builder.studio_ecosystem_npc_transit import (
                        replay_npc_transit,
                    )
                    from skeleton.ai.game_builder.studio_ecosystem_npc_transit_editor import (
                        load_npc_transit_editor_export,
                    )
                    if args.baseline_transit is None:
                        raise StudioQuestError("NPC transit import requires original receipt")
                    original = replay_npc_transit(
                        docs, _strict(args.baseline_transit, max_bytes=262144),
                        authorized=True)
                    if (original["temporal_receipt"] != temporal
                            or original["source_digest"] != args.expected_source):
                        raise StudioQuestError("stale NPC transit editor baseline")
                    graph = load_npc_transit_editor_export(
                        args.import_graph, authorized=True,
                        expected_project_id=original["project_id"],
                        expected_source_digest=original["source_digest"],
                        expected_session_digest=original["session_digest"],
                        expected_temporal_digest=original["temporal_digest"],
                        expected_baseline_digest=original["transit_digest"])
                else:
                    if args.baseline_transit is not None:
                        raise StudioQuestError("baseline receipt only valid with import")
                    graph = _strict(args.graph, max_bytes=32768)
                result = compile_npc_transit(
                    docs, temporal, graph, authorized=True)
        output = {"transit": result}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_npc_transit_editor import (
                publish_npc_transit_editor,
            )
            output["editor"] = publish_npc_transit_editor(
                docs, result, args.editor_directory, authorized=True)
        if args.playable_manifest:
            output["playable_handoff"] = compile_transit_playable(
                docs, result, authorized=True)
        if args.publish:
            output["publication"] = publish_npc_transit(
                docs, result, args.publish, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
