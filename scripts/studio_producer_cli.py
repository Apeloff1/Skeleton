"""Operator-only read/probe CLI for the original offline game production plane.

This is not an automated game publishing or release workflow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_frame import production_frame
from skeleton.ai.game_builder.studio_ecosystem_quest import replay_quest
from skeleton.ai.game_builder.studio_ecosystem_social import replay_factions
from skeleton.ai.game_builder.studio_ecosystem_scene import inspect_scene, inspect_object_intent
from skeleton.ai.game_builder.studio_ecosystem_capacity import (
    observe_producer_capacity, plan_producer_admission,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise StudioQuestError("ambiguous repeated JSON key")
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Inspect sandbox-only original game-production work")
    parser.add_argument("--project", required=True, help="Registered studio source ID")
    parser.add_argument("--quest-actions",default="[]",
                        help="JSON array of exact authored [stage, choice] replay pairs")
    parser.add_argument("--social-choice",action="append",default=[],
                        help="One separate authored faction decision (repeatable)")
    parser.add_argument("--scene",help="Read one authored scene at current quest progress")
    parser.add_argument("--object",dest="object_id",
                        help="Inspect an interactive object intent in the selected scene")
    parser.add_argument("--capacity-root",type=Path,
                        help="Existing local directory for read-only CPU/RAM/disk capacity observation")
    parser.add_argument("--working-set-bytes",type=int)
    parser.add_argument("--output-bytes",type=int)
    args=parser.parse_args(argv)
    if args.object_id and not args.scene:
        parser.error("--object requires --scene")
    if args.capacity_root is None and (
        args.working_set_bytes is not None or args.output_bytes is not None
    ):
        parser.error("capacity job sizes require --capacity-root")
    if args.capacity_root is not None and (
        args.working_set_bytes is None or args.output_bytes is None
    ):
        parser.error("--capacity-root requires both resource job sizes")
    if len(args.quest_actions.encode("utf-8")) > 65536:
        parser.error("quest action JSON too large for single CLI invocation")
    try:
        actions=json.loads(args.quest_actions,object_pairs_hook=_strict_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               StudioQuestError("nonfinite actions")))
        docs=read_blueprint(args.project)
        session=replay_quest(docs,actions,authorized=True)
        report={"production":production_frame(docs,session,authorized=True),
                "social":replay_factions(docs,args.social_choice,authorized=True)}
        if args.scene:
            report["scene"]=inspect_scene(session,docs,scene_id=args.scene,authorized=True)
        if args.object_id:
            report["object_intent"]=inspect_object_intent(
                session,docs,scene_id=args.scene,object_id=args.object_id,
                authorized=True)
        if args.capacity_root is not None:
            report["capacity"]=plan_producer_admission(
                observe_producer_capacity(args.capacity_root),
                working_set_bytes=args.working_set_bytes,
                output_bytes=args.output_bytes,
            )
    except (StudioQuestError,ValueError,UnicodeError,PermissionError) as exc:
        parser.error(str(exc))
    print(json.dumps(report,sort_keys=True,ensure_ascii=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
