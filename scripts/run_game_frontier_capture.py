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
from skeleton.jeeves.game_frontier_native_audit import analyze_native_capture
from skeleton.jeeves.game_frontier_native_compare import compare_native_sessions
from skeleton.jeeves.game_frontier_native_rpg_bridge import (
    parse_native_rpg_pages,evaluate_native_rpg_timeline,
)


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
    parser.add_argument("operation",choices=("ingest","verify","fork","timeline","analyze","compare",
                                 "evaluate-events"),
                        help="Do not combine a new capture with replay or fork")
    parser.add_argument("--signed-gdd",type=Path,required=True)
    parser.add_argument("--scene-json",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--capture-jsonl",type=Path)
    parser.add_argument("--track",default="production")
    parser.add_argument("--fork-track")
    parser.add_argument("--through",type=int)
    parser.add_argument("--max-samples",type=int,default=1000000)
    parser.add_argument("--start-frame",type=int,default=0)
    parser.add_argument("--page-limit",type=int,default=128)
    parser.add_argument("--actor-id")
    parser.add_argument("--event-pages-json",type=Path)
    parser.add_argument("--event-flags-json",type=Path)
    parser.add_argument("--event-limit",type=int,default=256)
    parser.add_argument("--audit-max-frames",type=int,default=256)
    parser.add_argument("--other-journal",type=Path)
    parser.add_argument("--other-track",default="production")
    parser.add_argument("--comparison-max-frames",type=int,default=1024)
    parser.add_argument("--comparison-tolerance-m",type=float,default=.5)
    parser.add_argument("--acceleration-threshold",type=float,default=120.)
    parser.add_argument("--energy-delta-threshold",type=float,default=2000.)
    parser.add_argument("--chunk-x",type=int)
    parser.add_argument("--chunk-y",type=int)
    parser.add_argument("--changes-only",action="store_true")
    parser.add_argument("--resume",action="store_true",
                        help="Only reuse exact already-committed capture records")
    arguments=parser.parse_args(argv)
    if arguments.operation=="ingest" and arguments.capture_jsonl is None:
        parser.error("ingest requires --capture-jsonl")
    if arguments.operation=="fork" and (
        arguments.fork_track is None or arguments.through is None):
        parser.error("fork requires --fork-track and --through")
    if (arguments.chunk_x is None)!=(arguments.chunk_y is None):
        parser.error("timeline chunk filters require both --chunk-x and --chunk-y")
    if arguments.operation not in ("timeline","analyze","compare","evaluate-events") and (
        arguments.start_frame!=0 or arguments.actor_id is not None):
        parser.error("frame cursor and actor filter apply only to timeline/analyze")
    if arguments.operation!="timeline" and (
        arguments.page_limit!=128 or arguments.chunk_x is not None or
        arguments.changes_only):
        parser.error("chunk filters and page limit apply only to timeline")
    if arguments.operation!="analyze" and (
        arguments.audit_max_frames!=256 or arguments.acceleration_threshold!=120. or
        arguments.energy_delta_threshold!=2000.):
        parser.error("audit thresholds and budget apply only to analyze")
    if arguments.operation=="compare" and (
        arguments.other_journal is None or arguments.start_frame!=0):
        parser.error("compare requires --other-journal and no frame cursor")
    if arguments.operation!="compare" and (
        arguments.other_journal is not None or
        arguments.other_track!="production" or
        arguments.comparison_max_frames!=1024 or
        arguments.comparison_tolerance_m!=.5):
        parser.error("comparison options apply only to compare operation")
    if arguments.operation=="evaluate-events" and (
        arguments.event_pages_json is None or arguments.actor_id is None):
        parser.error("event evaluation requires --event-pages-json and --actor-id")
    if arguments.operation!="evaluate-events" and (
        arguments.event_pages_json is not None or arguments.event_flags_json is not None
        or arguments.event_limit!=256):
        parser.error("event pages, flags and evaluation limit only apply to evaluate-events")
    if arguments.operation!="ingest" and arguments.resume:
        parser.error("--resume applies only to ingest")
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
        specified=settings.get("actors")
        if specified is None:
            catalog={settings["actor_id"]:settings["actor_asset_digest"]}
        else:
            if (not isinstance(specified,list) or not 1<=len(specified)<=64 or
                not all(isinstance(item,dict) and
                        type(item.get("id")) is str and
                        type(item.get("source_digest")) is str
                        for item in specified)):
                raise ValueError("invalid signed multi-actor catalog")
            catalog={item["id"]:item["source_digest"] for item in specified}
            if (len(catalog)!=len(specified) or
                catalog.get(settings["actor_id"])!=settings["actor_asset_digest"]):
                raise ValueError("duplicate, missing, or forged primary actor catalog")
        with FrameReceiptJournal(arguments.journal,gdd,track=arguments.track) as journal:
            if arguments.operation=="ingest":
                worker=GodotPhysicsCaptureIngestor(
                    journal,candidate_digest=settings["candidate_digest"],
                    allowed_assets=catalog,max_samples=arguments.max_samples,
                    expected_reference_controls=settings.get("reference_controls"),
                    controlled_actor_id=settings["actor_id"],
                    expected_gameplay_zones=settings.get("gameplay_zones",()),
                    expected_gameplay_force_fields=settings.get("gameplay_force_fields",()))
                result=worker.ingest_file(arguments.capture_jsonl,
                                          resume=arguments.resume)
                report={"operation":"ingest",
                        "samples_committed":sum(not x.get("reused_existing",False)
                                                for x in result),
                        "samples_reused":sum(bool(x.get("reused_existing",False))
                                              for x in result),
                        "journal":journal.stats(),"replay":journal.replay()}
            elif arguments.operation=="verify":
                report={"operation":"verify","journal":journal.stats(),
                        "replay":journal.replay(through=arguments.through)}
            elif arguments.operation=="compare":
                with FrameReceiptJournal(arguments.other_journal,gdd,
                                         track=arguments.other_track) as other:
                    report={"operation":"compare","comparison":compare_native_sessions(
                        journal,other,actor_id=arguments.actor_id,
                        max_aligned_frames=arguments.comparison_max_frames,
                        tolerance_m=arguments.comparison_tolerance_m)}
            elif arguments.operation=="evaluate-events":
                raw_pages=_operator_json(arguments.event_pages_json)
                if ("source_actor_id" in raw_pages and
                    raw_pages["source_actor_id"]!=arguments.actor_id):
                    raise ValueError("event page source actor differs from selected game actor")
                if arguments.actor_id not in catalog:
                    raise ValueError("runtime event actor is absent from authorized scene catalog")
                initial=journal.native_sample(0)
                if (initial is None or
                    initial.get("scene_candidate_digest")!=settings["candidate_digest"] or
                    initial.get("signed_gdd_digest")!=gdd.source_digest or
                    {item["id"]:item["source_digest"]
                     for item in initial.get("actors",[])}!=catalog):
                    raise ValueError("event journal actor or scene identity differs from Forge source")
                pages=parse_native_rpg_pages(raw_pages)
                flags={}
                if arguments.event_flags_json is not None:
                    raw_flags=_operator_json(arguments.event_flags_json)
                    if (raw_flags.get("schema")!="skeleton.game.native_rpg_flags.v1"
                        or not isinstance(raw_flags.get("flags"),dict)
                        or any(type(v) is not bool
                               for v in raw_flags["flags"].values())):
                        raise ValueError("source-typed boolean RPG event flags required")
                    flags=raw_flags["flags"]
                report={"operation":"evaluate-events",
                        "evaluation":evaluate_native_rpg_timeline(
                            journal,pages,actor_id=arguments.actor_id,
                            start_frame=arguments.start_frame,
                            limit=arguments.event_limit,flags=flags)}
            elif arguments.operation=="analyze":
                report={"operation":"analyze","diagnostics":analyze_native_capture(
                    journal,start_frame=arguments.start_frame,
                    max_frames=arguments.audit_max_frames,
                    actor_id=arguments.actor_id,
                    acceleration_threshold_mps2=arguments.acceleration_threshold,
                    energy_change_threshold_j=arguments.energy_delta_threshold)}
            elif arguments.operation=="timeline":
                report={"operation":"timeline","page":journal.evidence_page(
                    start_frame=arguments.start_frame,limit=arguments.page_limit,
                    actor_id=arguments.actor_id,
                    chunk_xy=((arguments.chunk_x,arguments.chunk_y)
                              if arguments.chunk_x is not None else None),
                    changes_only=arguments.changes_only)}
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
