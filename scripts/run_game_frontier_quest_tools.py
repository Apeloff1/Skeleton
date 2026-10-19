#!/usr/bin/env python3
"""Operator CLI for verified replay, cold audit, quest HUD and branch comparison.

Uses the canonical signed GDD, native Godot journal and authored RPG pages.
No AI canon writes, auto world mutation, host GPS, or untrusted checkpoint
admission. 'batch' can store its new checkpoint exclusively to a safe path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts.run_game_frontier_capture import _operator_json
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from skeleton.jeeves.game_frontier_native_rpg_bridge import parse_native_rpg_pages
from skeleton.jeeves.game_frontier_native_quest_batch import replay_native_quest_batches
from skeleton.jeeves.game_frontier_native_quest_audit import audit_native_quest_checkpoint
from skeleton.jeeves.game_frontier_native_quest_inspector import inspect_native_quest_objectives
from skeleton.jeeves.game_frontier_native_quest_compare import compare_native_quest_outcomes


def _new_checkpoint(destination: Path, data: dict, *, sources: tuple[Path,...]) -> None:
    if (not destination.parent.is_dir() or destination.parent.is_symlink()
        or destination.exists() or destination.is_symlink()
        or destination.resolve() in {p.resolve() for p in sources}):
        raise ValueError("checkpoint destination must be a new regular file in existing folder")
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8") as output:
            json.dump(data,output,sort_keys=True,separators=(",",":"),allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main(argv:list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("batch","audit","inspect","compare"))
    parser.add_argument("--signed-gdd",type=Path,required=True)
    parser.add_argument("--scene-json",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--track",default="production")
    parser.add_argument("--actor-id",required=True)
    parser.add_argument("--event-pages-json",type=Path,required=True)
    parser.add_argument("--quest-graph-json",type=Path,required=True)
    parser.add_argument("--quest-approvals-json",type=Path,required=True)
    parser.add_argument("--checkpoint-input-json",type=Path)
    parser.add_argument("--checkpoint-output-json",type=Path)
    parser.add_argument("--expected-checkpoint-digest")
    parser.add_argument("--other-approvals-json",type=Path)
    parser.add_argument("--other-checkpoint-json",type=Path)
    parser.add_argument("--through",type=int)
    parser.add_argument("--frames-per-window",type=int,default=256)
    args=parser.parse_args(argv)
    if args.operation=="batch":
        if ((args.checkpoint_input_json is None)!=(args.expected_checkpoint_digest is None)
            or args.other_approvals_json is not None or args.other_checkpoint_json is not None):
            parser.error("batch resume requires a separately trusted checkpoint digest")
    else:
        if (args.checkpoint_input_json is None or args.expected_checkpoint_digest is not None
            or args.through is not None or args.checkpoint_output_json is not None):
            parser.error("audit/inspect/compare require one existing checkpoint only")
        if args.operation=="compare" and (
            args.other_approvals_json is None or args.other_checkpoint_json is None):
            parser.error("compare requires second approval and second checkpoint files")
        if args.operation!="compare" and (
            args.other_approvals_json is not None or args.other_checkpoint_json is not None):
            parser.error("second outcome files are only valid for compare")
    try:
        gdd=bind_signed_gdd(_operator_json(args.signed_gdd))
        scene=_operator_json(args.scene_json)
        settings=scene.get("native_capture")
        if (scene.get("schema")!="skeleton.game.frontier_godot_overlay.v1"
            or type(settings) is not dict or settings.get("enabled") is not True
            or settings.get("gdd_digest")!=gdd.source_digest
            or settings.get("candidate_digest")!=scene.get("origin_candidate_digest")
            or settings.get("actor_id")!=args.actor_id
            or settings.get("fps") not in (30,50,60,120)):
            raise ValueError("native source scene must be bound to signed GDD and selected actor")
        pages_json=_operator_json(args.event_pages_json)
        if (pages_json.get("source_actor_id",args.actor_id)!=args.actor_id):
            raise ValueError("source-authored event page actor mismatch")
        pages=parse_native_rpg_pages(pages_json)
        graph=_operator_json(args.quest_graph_json)
        approved=_operator_json(args.quest_approvals_json)
        with FrameReceiptJournal(args.journal,gdd,track=args.track) as journal:
            first=journal.native_sample(0)
            observed_catalog={x["id"]:x["source_digest"] for x in first.get("actors",[])} if first else {}
            expected_catalog=settings.get("actors")
            if expected_catalog is None:
                known={settings["actor_id"]:settings["actor_asset_digest"]}
            else:
                known={x["id"]:x["source_digest"] for x in expected_catalog}
                if len(known)!=len(expected_catalog):
                    raise ValueError("duplicate Forge scene actor source catalog")
            if (not first or first.get("scene_candidate_digest")!=settings["candidate_digest"]
                or first.get("signed_gdd_digest")!=gdd.source_digest
                or observed_catalog!=known or args.actor_id not in observed_catalog):
                raise ValueError("quest journal source catalog and scene are not the same")
            if args.operation=="batch":
                prior=(_operator_json(args.checkpoint_input_json,limit=48*1024*1024)
                       if args.checkpoint_input_json is not None else None)
                batch=replay_native_quest_batches(
                    journal,pages,graph,approved,actor_id=args.actor_id,
                    scene_candidate_digest=settings["candidate_digest"],
                    through_frame=args.through,frames_per_window=args.frames_per_window,
                    resume_checkpoint=prior,
                    expected_checkpoint_digest=args.expected_checkpoint_digest)
                if args.checkpoint_output_json is not None:
                    _new_checkpoint(args.checkpoint_output_json,
                                    batch["head_checkpoint"],sources=(
                                        args.journal,args.signed_gdd,args.scene_json,
                                        args.event_pages_json,args.quest_graph_json,
                                        args.quest_approvals_json))
                result={"operation":"batch","gameplay":batch,
                        "checkpoint_file":(
                            str(args.checkpoint_output_json)
                            if args.checkpoint_output_json is not None else None)}
            else:
                checkpoint=_operator_json(args.checkpoint_input_json,limit=48*1024*1024)
                proof=audit_native_quest_checkpoint(
                    journal,pages,graph,approved,checkpoint,
                    actor_id=args.actor_id,scene_candidate_digest=settings["candidate_digest"],
                    frames_per_window=args.frames_per_window)
                if args.operation=="audit":
                    result={"operation":"audit","checkpoint_audit":proof}
                elif args.operation=="inspect":
                    report=inspect_native_quest_objectives(
                        journal,pages,graph,approved,checkpoint,proof,
                        actor_id=args.actor_id,scene_candidate_digest=settings["candidate_digest"])
                    result={"operation":"inspect","quest_journal":report}
                else:
                    other_approved=_operator_json(args.other_approvals_json)
                    other_checkpoint=_operator_json(args.other_checkpoint_json,limit=48*1024*1024)
                    compared=compare_native_quest_outcomes(
                        journal,journal,pages,graph,approved,other_approved,
                        checkpoint,other_checkpoint,
                        actor_id=args.actor_id,
                        scene_candidate_digest=settings["candidate_digest"])
                    result={"operation":"compare","outcome_difference":compared}
        print(json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        print(f"native gameplay operations rejected: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
