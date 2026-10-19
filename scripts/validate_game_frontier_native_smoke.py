#!/usr/bin/env python3
"""Evidence-based acceptance of actual Godot 4 native physics JSONL.

This program reads an explicitly selected game-native physics trace from the
operator's local game run. It proves the trace is internally coherent and
the controlled actor moved, not that a GPU rendered successfully or that
a hostile client could not forge local samples. A fixed SHA-pinned engine
run and the canonical signed-GDD journal are separate required evidence.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from skeleton.jeeves.game_frontier_native_chunks import (
    inspect_native_chunks,compare_native_chunk_transitions,NativeChunkError,
)
from skeleton.jeeves.game_frontier_frame_coherence import digest


class NativeSmokeError(ValueError):
    pass


def validate_native_trace(
    capture: Path, scene: Path, *, min_ticks: int = 4,
    max_ticks: int = 6000,
    minimum_actor_displacement_m: float = 0.01,
) -> dict:
    if (type(min_ticks) is not int or type(max_ticks) is not int or
        not 2<=min_ticks<=max_ticks<=1_000_000 or
        type(minimum_actor_displacement_m) not in (int,float) or
        not math.isfinite(minimum_actor_displacement_m) or
        not 0<minimum_actor_displacement_m<=100):
        raise NativeSmokeError("bounded native runtime acceptance parameters required")
    for path in (capture,scene):
        if not path.is_file() or path.is_symlink():
            raise NativeSmokeError("explicit regular native capture and scene files required")
    if scene.stat().st_size>24*1024*1024:
        raise NativeSmokeError("oversized native scene")
    project=json.loads(scene.read_text(encoding="utf-8"))
    settings=project.get("native_capture") if isinstance(project,dict) else None
    if (not isinstance(settings,dict) or
        settings.get("enabled") is not True or
        project.get("schema")!="skeleton.game.frontier_godot_overlay.v1" or
        settings.get("candidate_digest")!=project.get("origin_candidate_digest") or
        settings.get("fps") not in (30,50,60,120)):
        raise NativeSmokeError("unqualified game-native capture scene")
    actors=settings.get("actors")
    if not isinstance(actors,list) or not actors:
        actors=[{"id":settings["actor_id"],
                 "source_digest":settings["actor_asset_digest"]}]
    catalog={item["id"]:item["source_digest"] for item in actors}
    if len(catalog)!=len(actors) or not 1<=len(catalog)<=64:
        raise NativeSmokeError("duplicate or excessive actor catalog")
    primary=settings["actor_id"]
    if catalog.get(primary)!=settings["actor_asset_digest"]:
        raise NativeSmokeError("missing authoritative simulated game actor")
    units=float(settings.get("chunk_size_m",32.))
    if not .1<=units<=1e5:
        raise NativeSmokeError("native source chunk resolution invalid")
    previous=None
    start=None
    finish=None
    observed_chunks=set()
    observed_migrations=0
    observed_contact_actors=0
    trace_root=sha256()
    count=0
    with capture.open("rb") as source:
        for raw in source:
            if len(raw)>128*1024:
                raise NativeSmokeError("native trace line exceeds verification budget")
            if count>=max_ticks:
                raise NativeSmokeError("native trace exceeds allowed tick budget")
            trace_root.update(raw)
            try:
                record=json.loads(raw)
            except (ValueError,UnicodeError,TypeError) as exc:
                raise NativeSmokeError("invalid UTF-8 native physics observation") from exc
            if (not isinstance(record,dict) or
                record.get("schema")!="skeleton.game.native_physics_observation.v1" or
                record.get("native_engine")!="godot4_physics" or
                record.get("authority")!="untrusted_native_candidate_observation_not_attested" or
                record.get("scene_candidate_digest")!=settings["candidate_digest"] or
                record.get("signed_gdd_digest")!=settings["gdd_digest"] or
                record.get("fps")!=settings["fps"] or
                type(record.get("native_tick")) is not int or
                record["native_tick"]!=count or
                type(record.get("ticks_usec")) is not int or
                record["ticks_usec"]<0 or
                len(record.get("actors",[]))!=len(catalog)):
                raise NativeSmokeError("native engine trace schema/tick/source mismatch")
            incoming={row["id"]:row for row in record["actors"]}
            if len(incoming)!=len(catalog) or any(
                name not in incoming or
                incoming[name].get("source_digest")!=source_digest
                for name,source_digest in catalog.items()
            ):
                raise NativeSmokeError("native actor/source identity mismatch")
            for row in incoming.values():
                contacts=row.get("contact_count")
                if contacts is None or type(contacts) is not int or not 0<=contacts<=64:
                    raise NativeSmokeError("native engine contact observation missing")
                observed_contact_actors+=int(contacts>0)
            try:
                partition=inspect_native_chunks(record,
                    expected_chunk_size_m=units,require_native_partition=True)
                motion=compare_native_chunk_transitions(
                    record,previous=previous,expected_chunk_size_m=units)
            except NativeChunkError as exc:
                raise NativeSmokeError("native per-chunk physics evidence inconsistent") from exc
            observed_chunks.update(tuple(x["chunk_xy"]) for x in partition["chunks"])
            observed_migrations+=motion["migrations"]
            coordinate=incoming[primary]["world_xyz_m"]
            if start is None:
                start=coordinate
            finish=coordinate
            if previous is not None and record["ticks_usec"]<=previous["ticks_usec"]:
                raise NativeSmokeError("Godot native monotone physics timestamp regressed")
            previous=record
            count+=1
    if count<min_ticks:
        raise NativeSmokeError("native game did not emit enough fixed physics ticks")
    motion=math.dist(start,finish)
    if motion<minimum_actor_displacement_m:
        raise NativeSmokeError("native reference RigidBody3D did not actually move")
    report={
        "schema":"skeleton.game.godot_native_trace_qualification.v1",
        "fixed_physics_ticks_observed":count,
        "fps":settings["fps"],
        "actors_observed_each_tick":len(catalog),
        "controlled_actor":primary,
        "controlled_displacement_m":motion,
        "distinct_game_chunks_observed":len(observed_chunks),
        "cross_chunk_migrations_observed":observed_migrations,
        "positive_contact_count_observations":observed_contact_actors,
        "source_capture_sha256":trace_root.hexdigest(),
        "signed_gdd_digest":settings["gdd_digest"],
        "candidate_digest":settings["candidate_digest"],
        "verification":"native_JSONL_internal_consistency_not_GPU_attestation",
    }
    report["receipt_digest"]=digest(report)
    return report


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-jsonl",required=True,type=Path)
    parser.add_argument("--scene-json",required=True,type=Path)
    parser.add_argument("--min-ticks",type=int,default=4)
    parser.add_argument("--max-ticks",type=int,default=6000)
    args=parser.parse_args(argv)
    try:
        report=validate_native_trace(args.capture_jsonl,args.scene_json,
            min_ticks=args.min_ticks,max_ticks=args.max_ticks)
    except (ValueError,TypeError,KeyError,IndexError,OSError) as exc:
        print(f"Game Frontier native trace rejected: {exc}",file=sys.stderr)
        return 2
    print(json.dumps(report,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
