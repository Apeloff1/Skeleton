#!/usr/bin/env python3
"""Verify independently recorded virtual game instruments against real Godot.

The instrument JSONL data is reconstructed from the authenticated GDD's
source journal of captured native physics; it is not trusted merely because
Godot produced a second file. No device GPS or real navigation is used.
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
from skeleton.jeeves.game_frontier_native_instrument_trace import verify_native_instrument_trace


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signed-gdd",type=Path,required=True)
    parser.add_argument("--scene-json",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--telemetry-jsonl",type=Path,required=True)
    parser.add_argument("--actor-id",required=True)
    parser.add_argument("--track",default="production")
    parser.add_argument("--max-frames",type=int,default=1000000)
    opts=parser.parse_args(argv)
    try:
        gdd=bind_signed_gdd(_operator_json(opts.signed_gdd))
        scene=_operator_json(opts.scene_json)
        capture=scene.get("native_capture")
        advanced=scene.get("advanced_physics")
        if (scene.get("schema")!="skeleton.game.frontier_godot_overlay.v1"
            or type(capture) is not dict or capture.get("enabled") is not True
            or capture.get("candidate_digest")!=scene.get("origin_candidate_digest")
            or capture.get("gdd_digest")!=gdd.source_digest
            or capture.get("actor_id")!=opts.actor_id
            or type(advanced) is not dict
            or type(advanced.get("airflow_velocity_xyz")) is not list
            or opts.telemetry_jsonl.is_symlink()):
            raise ValueError("scene/GDD/source actor/virtual airflow must match")
        with FrameReceiptJournal(opts.journal,gdd,track=opts.track) as journal:
            with opts.telemetry_jsonl.open("r",encoding="utf-8") as source:
                proof=verify_native_instrument_trace(
                    journal,source,actor_id=opts.actor_id,
                    scene_candidate_digest=capture["candidate_digest"],
                    expected_airflow_xyz_mps=advanced["airflow_velocity_xyz"],
                    expected_fps=capture["fps"],max_frames=opts.max_frames)
        print(json.dumps(proof,sort_keys=True,separators=(",",":"),allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,IndexError,OSError) as exc:
        print(f"Godot virtual instrument proof rejected: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
