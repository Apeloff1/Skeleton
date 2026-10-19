#!/usr/bin/env python3
"""Materialize an explicitly scoped Godot native physics smoke project.

Uses the current source-test GDD/physics fixture to exercise the *actual*
Forge exporter and importer on a real Godot binary in a specialized job.
Not a user game or a claim of completed cinematic/gameplay production.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from tests.test_game_frontier_advanced_scene import scene_params
from tests.test_game_frontier_position_frames import gdd
from skeleton.jeeves.game_frontier_frame_coherence import (
    bind_signed_gdd,FrameObject,
)
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.forge.game_frontier_godot import emit_frontier_godot_overlay


def build_smoke_project(out:Path, *, fps:int=60, frames:int=20) -> dict:
    if (not out.is_dir() or out.is_symlink() or fps not in (30,50,60,120)
        or type(frames) is not int or not 2<=frames<=600):
        raise ValueError("explicit normal output folder, FPS and bounded frames required")
    bible=gdd()
    anchor=bind_signed_gdd(bible)
    cfg=scene_params()
    cfg["fps"]=fps
    cfg.update({
        "frame_gdd":anchor,"frame_index":0,
        "frame_objects":(
            FrameObject("hero",Vec3(0,0,30),Vec3(0,0,-20),"a"*64),
            FrameObject("island",Vec3(35,0,0),Vec3(0,0,0),"b"*64),
        ),
    })
    candidate=compile_frontier_scene(**cfg)
    overlay=emit_frontier_godot_overlay(
        candidate,cloud_path_duration_s=2,enable_native_capture=True,
        native_capture_all_actors=True,native_capture_max_frames=frames,
        enable_native_reference_controls=True,
        native_reference_test_drive_ticks=min(frames-1,12))
    project_godot='''config_version=5

[application]
config/name="Skeleton Frontier Native Smoke"
run/main_scene="res://frontier/frontier_scene.tscn"

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
'''
    overlay={"project.godot":project_godot,**overlay,
             "signed_gdd.json":json.dumps(bible,sort_keys=True)+"\n"}
    for filename,content in overlay.items():
        destination=out/filename
        if (not destination.resolve().is_relative_to(out.resolve())
            or destination.exists()):
            raise ValueError("would overwrite or escape native smoke project")
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(content,encoding="utf-8")
    return {
        "scene_digest":candidate.manifest_digest,
        "gdd_digest":anchor.source_digest,
        "actors":2,
        "fps":fps,
        "capture_frames":frames,
        "project":str(out),
        "authority":"explicit_native_smoke_fixture_not_finished_game",
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--fps",type=int,default=60)
    parser.add_argument("--frames",type=int,default=20)
    opts=parser.parse_args(argv)
    try:
        report=build_smoke_project(opts.output,fps=opts.fps,frames=opts.frames)
    except (ValueError,OSError) as exc:
        print(f"native smoke export blocked: {exc}",file=sys.stderr)
        return 2
    print(json.dumps(report,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
