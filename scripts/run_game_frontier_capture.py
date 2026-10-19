#!/usr/bin/env python3
"""Operator-controlled Godot game physics evidence: ingest, verify, rollback.

Consumes an explicitly selected signed GDD and a Forge-generated Godot
overlay's source map. No executable input or OS GPS/real-world coordinates.
The Godot project has to be installed/launched separately, with opt-in
native_capture enabled. The CLI NEVER claims the capture was hardware-
attested, a GPU rendering test, or a successfully completed game.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal


def _operator_json(path: Path, *, limit: int = 24*1024*1024) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("source must be an explicitly selected regular file")
    if path.stat().st_size > limit:
        raise ValueError("source data exceeds bounded file limit")
    parsed=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed,dict):
        raise ValueError("JSON object required")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("ingest","verify","fork"),
                        help="Do not combine a new capture with replay or fork")
    parser.add_argument("--signed-gdd",type=Path,required=True)
    parser.add_argument("--scene-json",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--capture-jsonl",type=Path)
    parser.add_argument("--track",default="production")
    parser.add_argument("--fork-track")
    parser.add_argument("--through",type=int)
    parser.add_argument("--max-samples",type=int,default=1000000)
    arguments=parser.parse_args(argv)
    if arguments.operation=="ingest" and arguments.capture_jsonl is None:
        parser.error("ingest requires --capture-jsonl")
    if arguments.operation=="fork" and (
        arguments.fork_track is None or arguments.through is None):
        parser.error("fork requires --fork-track and --through")
    if arguments.operation!="ingest" and arguments.capture_jsonl is not None:
        parser.error("capture input is only valid for ingest")
    try:
        gdd=bind_signed_gdd(_operator_json(arguments.signed_gdd))
        source=_operator_json(arguments.scene_json)
        settings=source.get("native_capture")
        if (source.get("schema")!="skeleton.game.frontier_godot_overlay.v1"
            or not isinstance(settings,dict) or
            settings.get("enabled") is not True or
            settings.get("gdd_digest")!=gdd.source_digest or
            settings.get("candidate_digest")!=source.get("origin_candidate_digest") or
            settings.get("fps") not in (30,50,60,120)):
            raise ValueError("not a signed-GDD-linked opt-in Godot source overlay")
        catalog={settings["actor_id"]:settings["actor_asset_digest"]}
        with FrameReceiptJournal(arguments.journal,gdd,track=arguments.track) as journal:
            if arguments.operation=="ingest":
                worker=GodotPhysicsCaptureIngestor(
                    journal,candidate_digest=settings["candidate_digest"],
                    allowed_assets=catalog,max_samples=arguments.max_samples)
                result=worker.ingest_file(arguments.capture_jsonl)
                report={"operation":"ingest","samples_committed":len(result),
                        "journal":journal.stats(),"replay":journal.replay()}
            elif arguments.operation=="verify":
                report={"operation":"verify","journal":journal.stats(),
                        "replay":journal.replay(through=arguments.through)}
            else:
                journal.fork(arguments.fork_track,through=arguments.through)
                report={"operation":"fork","source_track":arguments.track,
                        "new_track":arguments.fork_track,
                        "through":arguments.through,"source_replay":journal.replay()}
        print(json.dumps(report,sort_keys=True,separators=(",",":")))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f"game frontier native evidence rejected: {error}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
