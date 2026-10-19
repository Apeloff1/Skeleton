#!/usr/bin/env python3
"""Run measured native game-session persistence/recovery endurance qualification.

No vague time claim: each cycle actually uses a cold replay, SQLite FULL/WAL
save/rollback, closes the vault, reopens it and independently recovers. This
does not certify months-long OS uptime or simulate model GPU workloads.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts.run_game_frontier_capture import _operator_json
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from skeleton.jeeves.game_frontier_native_rpg_bridge import parse_native_rpg_pages
from skeleton.jeeves.game_frontier_native_endurance import exercise_native_session_endurance


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("signed-gdd","scene-json","journal","event-pages-json",
                 "quest-graph-json","quest-approvals-json","vault"):
        p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--actor-id",default="hero")
    p.add_argument("--track",default="production")
    p.add_argument("--cycles",type=int,default=16)
    p.add_argument("--frames-per-window",type=int,default=4)
    p.add_argument("--retain-latest",type=int,default=2)
    p.add_argument("--crash-interval",type=int,default=4)
    p.add_argument("--max-cycle-ms",type=int)
    p.add_argument("--max-vault-bytes",type=int)
    args=p.parse_args(argv)
    try:
        anchor=bind_signed_gdd(_operator_json(args.signed_gdd))
        scene=_operator_json(args.scene_json)
        settings=scene.get("native_capture")
        if (scene.get("schema")!="skeleton.game.frontier_godot_overlay.v1"
            or type(settings) is not dict or settings.get("enabled") is not True
            or settings.get("gdd_digest")!=anchor.source_digest
            or settings.get("candidate_digest")!=scene.get("origin_candidate_digest")
            or settings.get("actor_id")!=args.actor_id):
            raise ValueError("source-bound Godot actor/GDD required for qualification")
        page_source=_operator_json(args.event_pages_json)
        if page_source.get("source_actor_id",args.actor_id)!=args.actor_id:
            raise ValueError("RPG authored pages must target selected source actor")
        pages=parse_native_rpg_pages(page_source)
        quest_graph=_operator_json(args.quest_graph_json)
        approvals=_operator_json(args.quest_approvals_json)
        with FrameReceiptJournal(args.journal,anchor,track=args.track) as journal:
            native=journal.native_sample(0)
            expected=settings.get("actors")
            catalog=({x["id"]:x["source_digest"] for x in expected}
                     if expected is not None else
                     {settings["actor_id"]:settings["actor_asset_digest"]})
            if (native is None or len(catalog)!=(
                len(expected) if expected is not None else 1) or
                native.get("scene_candidate_digest")!=settings["candidate_digest"]
                or {a["id"]:a["source_digest"] for a in native["actors"]}!=catalog):
                raise ValueError("Godot native source actor catalog identity mismatch")
            report=exercise_native_session_endurance(
                journal,pages,quest_graph,approvals,
                actor_id=args.actor_id,scene_candidate_digest=settings["candidate_digest"],
                vault_path=args.vault,cycles=args.cycles,
                window_frames=args.frames_per_window,retain_latest=args.retain_latest,
                crash_interval=args.crash_interval,
                max_cycle_ms=args.max_cycle_ms,max_vault_bytes=args.max_vault_bytes)
        print(json.dumps(report,sort_keys=True,separators=(",",":")))
        return 0
    except (ValueError,TypeError,KeyError,IndexError,OSError) as error:
        print(f"Game Frontier endurance qualification rejected: {error}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
