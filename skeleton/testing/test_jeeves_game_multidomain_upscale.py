"""Integration and adversarial tests of actual Jeeves multidomain upscale outputs."""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import struct
import wave

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer.jeeves_game_upscale_queue import record_output
from skeleton.jeeves.game_console_assets import decode_png, png_rgba


def workspace(tmp_path: Path) -> Path:
    output = run_game_cli(["init","upscale-studio","--dir",str(tmp_path),
                           "--vision","A complete original atmospheric 2.5D game"])
    assert output["ok"], output
    return tmp_path / "upscale-studio"


def command(root: Path, action: str, *params: str):
    return run_game_cli(["jeeves",action,"--project",str(root),*params])


def sprite(root: Path, name: str = "sprite.png", *, w:int=8, h:int=8) -> Path:
    pixels=bytearray(w*h*4)
    for y in range(2,h-2):
        for x in range(2,w-2):
            p=(y*w+x)*4
            pixels[p:p+4]=bytes((75+x*12, 100+y*8, 35, 255))
    path=root/"assets"/name
    path.write_bytes(png_rgba(bytes(pixels),w,h))
    return path


def wav(root:Path,name:str, *, amplify:float=1.0) -> Path:
    samples=[int(1200*amplify*math.sin(i*math.pi/18)) for i in range(1800)]
    raw=struct.pack("<"+"h"*len(samples),*samples)
    file=root/"assets"/name
    stream=io.BytesIO()
    with wave.open(stream,"wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(raw)
    file.write_bytes(stream.getvalue())
    return file


def stage_source(root:Path, *, depth="2_5d", yaw=18.0) -> Path:
    sprite(root,"background.png")
    spec={
        "schema":"skeleton.jeeves.stage_source.v1",
        "grid":[
            "########",
            "#S.....#",
            "#.####.#",
            "#...#..#",
            "###.#..#",
            "#...#..#",
            "#....G.#",
            "########"
        ],
        "depth":depth,"biome":"forest",
        "layers":[
            {"path":"assets/background.png","depth":0.0},
            {"path":"assets/background.png","depth":0.8}
        ],
        "camera":{"yaw":yaw,"pitch":5.0}
    }
    path=root/"design"/"forest-stage.json"
    path.write_text(json.dumps(spec),encoding="utf-8")
    return path


def test_static_sprite_becomes_real_loopable_animated_detail_shadow(tmp_path):
    root=workspace(tmp_path)
    source=sprite(root)
    args=["--target","snes","--source","assets/sprite.png",
          "--output","assets/tree-animated.png","--frames","8","--pattern","wind"]
    preview=command(root,"upscale-animation",*args,"--dry-run")
    assert preview["ok"], preview
    assert not (root/"assets"/"tree-animated.png").exists()
    rendered=command(root,"upscale-animation",*args)
    assert rendered["ok"], rendered
    assert rendered["static_animated"] and rendered["contact_shadow_layer"]
    assert rendered["detail_enhanced"] and rendered["output_frames"]==8
    w,h,rgba=decode_png((root/"assets"/"tree-animated.png").read_bytes())
    assert (w,h)==(8,64)
    assert rgba[:8*8*4]==rgba[-8*8*4:]
    assert source.is_file()
    assert rendered["training_candidate"]["priority"]=="P1"
    assert not command(root,"upscale-animation",*args)["ok"]


def test_existing_animation_sheet_receives_multi_frame_detail(tmp_path):
    root=workspace(tmp_path)
    original=sprite(root,w=8,h=8)
    _,_,pixels=decode_png(original.read_bytes())
    (root/"assets"/"poses.png").write_bytes(png_rgba(pixels*2,8,16))
    improved=command(root,"upscale-animation","--target","nes",
                     "--source","assets/poses.png","--output","assets/poses-hd.png",
                     "--frame-height","8","--frames","8","--pattern","shimmer")
    assert improved["ok"], improved
    assert improved["source_frames"]==2
    assert improved["output_frames"]==8
    assert improved["independent_temporal_review"] is False


def test_shadow_shifts_contact_without_replacing_original(tmp_path):
    root=workspace(tmp_path)
    sprite(root)
    rendered=command(root,"upscale-shadow","--target","nes",
                     "--source","assets/sprite.png","--output","assets/shadow.png",
                     "--distance","2")
    assert rendered["ok"], rendered
    w,h,rgba=decode_png((root/"assets"/"shadow.png").read_bytes())
    assert (w,h)==(8,8)
    assert rgba[(2*w+2)*4:(2*w+2)*4+4]==bytes((99,116,35,255))
    assert rendered["contact_shadow_offset"]==2
    assert not rendered["independent_lighting_evaluation"]


@pytest.mark.parametrize("focus,action", [
    ("world","upscale-world"), ("environment","upscale-environment"),
    ("clutter","upscale-clutter"), ("foliage","upscale-stage"),
    ("shadow","upscale-stage"),
])
def test_stage_upscaler_enhances_biome_without_breaking_route(tmp_path,focus,action):
    root=workspace(tmp_path)
    stage_source(root)
    opts=["--target","snes","--source","design/forest-stage.json",
          "--output","design/enhanced-stage.json","--richness","5"]
    if action=="upscale-stage":
        opts+=["--focus",focus]
    result=command(root,action,*opts)
    assert result["ok"], result
    assert result["collision_map_unchanged"]
    assert result["camera"]["camera_rotation_supported"]
    enhanced=json.loads((root/"design"/"enhanced-stage.json").read_text())
    original=json.loads((root/"design"/"forest-stage.json").read_text())
    assert original["grid"]==enhanced["grid"]
    assert enhanced["enhancement"]["route_verified"]
    assert result["navigable_route_steps"]>=2
    for object_ in enhanced["enhancement"]["dressing"]:
        assert object_["collidable"] is False
        assert original["grid"][object_["y"]][object_["x"]]=="."


def test_unreachable_stage_fails_instead_of_fabricating_a_gameplay_pass(tmp_path):
    root=workspace(tmp_path)
    source=stage_source(root)
    data=json.loads(source.read_text())
    data["grid"]=[
        "########", "#S######", "########", "########",
        "########", "########", "######G#", "########",
    ]
    source.write_text(json.dumps(data))
    result=command(root,"upscale-stage","--target","snes",
                   "--source","design/forest-stage.json",
                   "--output","design/blocked.json")
    assert result["ok"] is False
    assert "traversable" in result["error"]
    assert not (root/"design"/"blocked.json").exists()


@pytest.mark.parametrize("depth,yaw,pitch,allowed", [
    ("2d",0,0,True),("2d",5,0,False),
    ("2_5d",35,10,True),("2_5d",65,0,False),
    ("2_9d",80,30,True),("2_9d",100,0,False),
    ("3d",175,65,True),
])
def test_camera_rotation_respects_depth_grammar(tmp_path,depth,yaw,pitch,allowed):
    root=workspace(tmp_path)
    result=command(root,"camera-plan","--depth",depth,
                   "--yaw",str(yaw),"--pitch",str(pitch),
                   "--parallax-planes","5")
    assert result["ok"] is allowed
    if allowed:
        assert len(result["rotation_matrix"])==3
        assert len(result["parallax_depth_weights"])==5
        assert result["occlusion_test_required"]==(depth!="2d")


def test_real_multiplane_parallax_composites_authored_pixels(tmp_path):
    root=workspace(tmp_path)
    red=bytes((250,0,0,255))*64
    blue=bytes((0,0,250,120))*64
    (root/"assets"/"red.png").write_bytes(png_rgba(red,8,8))
    (root/"assets"/"blue.png").write_bytes(png_rgba(blue,8,8))
    doc={
        "schema":"skeleton.jeeves.parallax.v1","width":8,"height":8,
        "layers":[{"path":"assets/red.png","depth":1.0},
                  {"path":"assets/blue.png","depth":0.0}]
    }
    (root/"design"/"planes.json").write_text(json.dumps(doc))
    result=command(root,"upscale-parallax","--target","snes",
                   "--source","design/planes.json","--output","assets/composite.png",
                   "--pan","2")
    assert result["ok"],result
    assert len(result["planes"])==2
    assert {r["camera_shift_px"] for r in result["planes"]}=={0,2}
    assert result["composited_original_pixels"]
    w,h,rgba=decode_png((root/"assets"/"composite.png").read_bytes())
    assert (w,h)==(8,8)
    assert any(v for v in rgba)


@pytest.mark.parametrize("mode",["remaster","cinematic"])
def test_music_upscale_creates_real_pcm_and_prioritized_candidate(tmp_path,mode):
    root=workspace(tmp_path)
    wav(root,"theme.wav")
    result=command(root,"upscale-music","--target","snes",
                   "--source","assets/theme.wav","--output","assets/enhanced.wav",
                   "--mode",mode)
    assert result["ok"],result
    assert result["source_frames"]==result["output_frames"]==1800
    assert result["measured_output_peak"]>result["measured_source_peak"]
    assert result["training_candidate"]["priority"]=="P1"
    with wave.open(str(root/"assets"/"enhanced.wav"),"rb") as reader:
        assert reader.getnchannels()==1
        assert reader.getframerate()==22050
        assert reader.getnframes()==1800
    assert not result["music_quality_independently_reviewed"]


def test_ambient_stem_requires_real_matching_pcm_and_preserves_length(tmp_path):
    root=workspace(tmp_path)
    wav(root,"theme.wav")
    wav(root,"rain.wav",amplify=0.15)
    out=command(root,"upscale-music","--target","snes",
                "--source","assets/theme.wav","--output","assets/wet-theme.wav",
                "--mode","ambience","--ambience","assets/rain.wav")
    assert out["ok"],out
    assert out["ambience_stem_sha256"] == hashlib.sha256(
        (root/"assets"/"rain.wav").read_bytes()).hexdigest()
    missing=command(root,"upscale-music","--target","snes",
                    "--source","assets/theme.wav","--output","assets/no-stem.wav",
                    "--mode","ambience")
    assert not missing["ok"]
    assert not (root/"assets"/"no-stem.wav").exists()


def test_review_reparses_every_actual_project_asset_without_fake_quality(tmp_path):
    root=workspace(tmp_path)
    sprite(root)
    wav(root,"song.wav")
    stage_source(root)
    inventory=command(root,"asset-inventory","--page","0","--page-size","1")
    assert inventory["ok"],inventory
    assert inventory["total_assets_and_design_files"]>=3
    assert inventory["next_page"]==1
    seen=[]
    page=0
    while page is not None:
        result=command(root,"asset-inventory","--page",str(page),"--page-size","2")
        seen+=result["entries"]
        page=result["next_page"]
    assert len(seen)==inventory["total_assets_and_design_files"]
    assert all(len(r["sha256"])==64 for r in seen)
    result=command(root,"upscale-review","--passes","4")
    assert result["ok"],result
    assert len(result["passes"])==4
    assert result["complete_asset_inventory_reparsed"]
    assert all(row["files_rechecked"]==len(seen) for row in result["passes"])
    assert not result["all_assets_expert_reviewed"]
    assert not result["production_qualified"]


def test_upscaled_training_queue_prioritizes_failed_outputs_but_does_not_train(tmp_path):
    root=workspace(tmp_path)
    sprite(root)
    command(root,"upscale-animation","--target","nes",
            "--source","assets/sprite.png","--output","assets/motion.png")
    before=command(root,"queue-upscaled-training")
    assert before["ok"],before
    assert before["total_candidates"]==1
    assert before["candidates"][0]["priority"]=="P1"
    assert not before["neural_model_trained"]
    source_sha=hashlib.sha256((root/"assets"/"sprite.png").read_bytes()).hexdigest()
    record_output(root,category="asset",source="assets/sprite.png",
                  output="assets/motion.png",input_sha256=source_sha,
                  output_sha256=before["candidates"][0]["output_sha256"],
                  target="nes",quality="failed")
    after=command(root,"queue-upscaled-training","--page-size","1")
    assert after["total_candidates"]==2
    assert after["candidates"][0]["priority"]=="P0"
    assert after["next_page"]==1
    assert after["candidates"][0]["needs_independent_critique"]


def test_candidate_tampering_fails_closed(tmp_path):
    root=workspace(tmp_path)
    sprite(root)
    out=command(root,"upscale-shadow","--target","nes",
                "--source","assets/sprite.png","--output","assets/cast.png")
    digest=out["training_candidate"]["candidate_sha256"]
    candidate=root/".jeeves"/"production"/"upscale_candidates"/(digest+".json")
    data=json.loads(candidate.read_text())
    data["priority"]="P3"
    candidate.write_text(json.dumps(data))
    denied=command(root,"queue-upscaled-training")
    assert denied["ok"] is False


@pytest.mark.parametrize("action,params",[
    ("upscale-animation",["--target","nes","--source","assets/a.png",
                           "--output","assets/b.png","--frames","999"]),
    ("camera-plan",["--depth","2_5d","--yaw","360"]),
    ("upscale-review",["--passes","0"]),
    ("asset-inventory",["--page-size","0"]),
    ("upscale-world",["--target","nes","--source","design/a.json",
                       "--output","design/b.json","--richness","6"]),
    ("queue-upscaled-training",["--mode","remaster"]),
])
def test_invalid_or_unrelated_options_fail_closed(tmp_path,action,params):
    root=workspace(tmp_path)
    result=command(root,action,*params)
    assert not result["ok"],result
