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
        native_reference_test_drive_ticks=min(frames-1,12),
        native_camera_follow=True,
        native_gameplay_force_fields=({
            "id":"reference_thermal_updraft","actor_id":"hero",
            "kind":"updraft",
            "center_xyz_m":list(candidate.manifest["advanced_physics"]["body"]["position_xyz"]),
            "radius_m":5., "acceleration_mps2":9.8,
        },),
        native_gameplay_zones=({
            "id":"spawn_marker", "actor_id":"hero",
            "center_xyz_m":list(candidate.manifest["advanced_physics"]["body"]["position_xyz"]),
            "radius_m":1.0,
            "event_page_id":"hero_spawn_region",
            "action_kind":"show_dialogue",
        },))
    project_godot='''config_version=5

[application]
config/name="Skeleton Frontier Native Smoke"
run/main_scene="res://frontier/frontier_scene.tscn"

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
'''
    # The native fixture must exercise actual observed physics -> RPG event
    # proposals, not only source Python synthetic event tests.
    pages={
        "schema":"skeleton.game.native_rpg_pages.v1",
        "pages":[
            {
                "id":"begin_sky_trial","priority":75,
                "conditions":[{"signal":"native_actor_speed_mps",
                               "comparison":"at_least","threshold":.2}],
                "actions":[
                    {"kind":"start_quest","channel":"quest",
                     "target":"hero","value":"sky_trial"},
                    {"kind":"set_flag","channel":"world",
                     "target":"hero","value":"quest_active=true"},
                    {"kind":"craft_item","channel":"character",
                     "target":"hero","value":"sky_trial_token"},
                    {"kind":"craft_item","channel":"character",
                     "target":"hero","value":"sky_trial_token"},
                    {"kind":"show_dialogue","channel":"ui",
                     "target":"hero","value":"The sky-island trial has begun."},
                    {"kind":"award_xp","channel":"character",
                     "target":"hero","value":"100"},
                    {"kind":"unlock_skill","channel":"character",
                     "target":"hero","value":"wind_dash:2"},
                    {"kind":"set_faction_reputation","channel":"character",
                     "target":"hero","value":"islanders:+25"},
                    {"kind":"set_npc_emotion","channel":"character",
                     "target":"hero","value":"island:curious"},
                    {"kind":"trigger_impact_fx","channel":"cinematic",
                     "target":"hero","value":"sky_trial_awaken_fx"},
                    {"kind":"change_camera","channel":"cinematic",
                     "target":"hero","value":"orbit"},
                    {"kind":"inspect_instrument","channel":"ui",
                     "target":"hero","value":"flight"},
                ],
                "required_flags":[],"cooldown_ms":0,"repeat":False,"enabled":True,
            },
            {
                "id":"complete_sky_trial","priority":70,
                "conditions":[{"signal":"native_gameplay_zone_exits",
                               "comparison":"at_least","threshold":1.}],
                "actions":[
                    {"kind":"advance_quest","channel":"quest",
                     "target":"hero","value":"sky_trial:finished"},
                    {"kind":"take_damage","channel":"character",
                     "target":"hero","value":"20"},
                    {"kind":"award_xp","channel":"character",
                     "target":"hero","value":"30"},
                    {"kind":"heal_health","channel":"character",
                     "target":"hero","value":"8"},
                    {"kind":"consume_item","channel":"character",
                     "target":"hero","value":"sky_trial_token"},
                ],
                "required_flags":[{"name":"quest_active","value":True}],
                "cooldown_ms":0,"repeat":False,"enabled":True,
            },
            {
                "id":"observed_actor_motion","priority":40,
                "conditions":[{"signal":"native_actor_speed_mps",
                               "comparison":"at_least","threshold":.2}],
                "actions":[{"kind":"show_dialogue","channel":"ui",
                            "target":"hero","value":"native motion confirmed"}],
                "required_flags":[],"cooldown_ms":0,"repeat":False,"enabled":True,
            },
            {
                "id":"entered_game_zone","priority":30,
                "conditions":[{"signal":"native_gameplay_zone_entries",
                               "comparison":"at_least","threshold":1.}],
                "actions":[{"kind":"save_bookmark","channel":"navigation",
                            "target":"hero","value":"zone_entered"}],
                "required_flags":[],"cooldown_ms":0,"repeat":False,"enabled":True,
            },
            {
                "id":"exited_game_zone","priority":30,
                "conditions":[{"signal":"native_gameplay_zone_exits",
                               "comparison":"at_least","threshold":1.}],
                "actions":[{"kind":"show_dialogue","channel":"ui",
                            "target":"hero","value":"zone exited"}],
                "required_flags":[],"cooldown_ms":0,"repeat":False,"enabled":True,
            },
        ],
    }
    # CI-only authoring fixture: actual native Godot contact/zone data must
    # choose which observed event receipts are explicitly approved later.
    # This is not a production authority or automated canon/world mutation.
    quest_graph={
        "schema":"skeleton.game.native_quest_graph.v1",
        "quests":[{
            "id":"sky_trial","title":"Reference Sky Island Trial",
            "start":"departed",
            "stages":[
                {"id":"departed","objective":"Cross the sky-island zone",
                 "next":["finished"]},
                {"id":"finished","objective":"Exit the sky-island zone",
                 "next":[]},
            ],
        }],
    }
    from skeleton.jeeves.game_frontier_native_quest_session import parse_native_quest_graph
    quest_graph=parse_native_quest_graph(quest_graph)
    overlay={"project.godot":project_godot,**overlay,
             "native_quest_graph.json":json.dumps(quest_graph,sort_keys=True)+"\n",
             "signed_gdd.json":json.dumps(bible,sort_keys=True)+"\n",
             "native_rpg_pages.json":json.dumps(pages,sort_keys=True)+"\n"}
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
