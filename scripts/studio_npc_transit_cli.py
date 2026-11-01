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
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore is not None:
        if args.prompt or args.graph is not None or args.temporal_receipt is not None:
            ap.error("restore cannot be combined with transit authoring")
    elif args.temporal_receipt is None or (args.prompt == (args.graph is not None)):
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
            result = (propose_npc_transit(
                docs, temporal, PROMPT, authorized=True)
                if args.prompt else compile_npc_transit(
                    docs, temporal, _strict(args.graph, max_bytes=32768),
                    authorized=True))
        output = {"transit": result}
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
