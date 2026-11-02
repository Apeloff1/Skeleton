"""Offline CLI for replay-verified NPC relay revision impact and custody."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_relay_impact import (
    PROMPT, MAX_BYTES, compile_npc_relay_impact, propose_npc_relay_impact,
    replay_npc_relay_impact, compile_npc_relay_impact_playable,
    publish_npc_relay_impact, restore_npc_relay_impact,
)
from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_npc_relay_impact_view import publish_npc_relay_impact_review


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound NPC relay impact review")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--candidate", type=Path)
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--render-review", type=Path,
                    help="Publish private script-free HTML impact review")
    ap.add_argument("--prompt", action="store_true")
    ap.add_argument("--playable", action="store_true")
    args = ap.parse_args(argv)
    if args.restore is not None:
        if args.baseline or args.candidate or args.publish or args.prompt:
            ap.error("restore excludes new comparison and publication")
    elif args.baseline is None or args.candidate is None:
        ap.error("comparison requires private baseline and candidate receipts")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            impact = restore_npc_relay_impact(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            baseline = _private_json(args.baseline, MAX_BYTES)
            candidate = _private_json(args.candidate, MAX_BYTES)
            kwargs = {"authorized": True,
                      "expected_source_digest": args.expected_source}
            impact = (propose_npc_relay_impact(
                docs, baseline, candidate, PROMPT, **kwargs)
                if args.prompt else compile_npc_relay_impact(
                    docs, baseline, candidate, **kwargs))
            replay_npc_relay_impact(docs, impact, authorized=True)
        result = {
            "schema": "skeleton.cli.studio_npc_relay_impact.v1",
            "impact": impact, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            result["playable_handoff"] = compile_npc_relay_impact_playable(
                docs, impact, authorized=True)
        if args.render_review is not None:
            result["review"] = publish_npc_relay_impact_review(
                docs, impact, args.render_review, authorized=True)
            result["file_write_performed"] = True
        if args.publish is not None:
            result["publication"] = publish_npc_relay_impact(
                docs, impact, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        ap.exit(2, f"NPC relay impact rejected: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
