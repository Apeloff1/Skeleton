"""Guaranteed maze style is a real native game, not an editor mock."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
import json,shutil,subprocess
import pytest

from skeleton.ai.webcrawler.dragon_native_targets import STYLES,target_catalog
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,plan_production,
    _render,make_source_release,verify_source_release,validate_native_source,
)
from skeleton.ai.webcrawler.dragon_route_maze import MazeRequest,build_maze,verify_maze


def original_maze_request(target:str="pc_linux",seed:int=1977):
    return ProductionRequest(
        title="Original Serpentine Maze Adventure",
        style="maze_route_adventure",
        targets=(target,),seed=seed,original_work_attested=True,
        portable_design=PortableGameDesign(
            stages=1,candidates=1,difficulty=7,
            campaign_pathing="branching",
            challenge_profile="spicy",
        ),
    )


def test_maze_style_only_advertises_real_desktop_c99_runtime_targets():
    assert "maze_route_adventure" in STYLES
    targets={row["id"]:row for row in target_catalog()}
    for system in ("pc_linux","pc_windows","pc_macos","steam_deck"):
        assert "maze_route_adventure" in targets[system]["supported_styles"]
        request=original_maze_request(system)
        assert plan_production(request)[0].state=="source_ready"
    for device in ("game_boy","game_boy_color","nes","ps1","xbox_original"):
        assert "maze_route_adventure" not in targets[device]["supported_styles"]
        assert plan_production(original_maze_request(device))[0].state=="blocked"


@pytest.mark.parametrize("target",["pc_linux","pc_windows","pc_macos","steam_deck"])
def test_native_pipeline_emits_actual_native_gameplay_with_every_room_certified(target):
    project=_render(original_maze_request(target),target)
    assert project.style=="maze_route_adventure"
    assert project.target_id==target
    validate_native_source(project)
    manifest=json.loads(project.files["dragon-native-manifest.json"])
    assert manifest["style"]=="maze_route_adventure"
    assert manifest["runtime_gameplay_mode"]=="native_original_world_routes"
    assert manifest["campaign_stages"]==1
    game=json.loads(project.files["dragon-original-route-proof.json"])
    assert game["constructive_maze_verification"]["status"]=="constructively_complete"
    assert game["constructive_maze_certificate"]["location_recovery_count"]==36
    assert len(game["probes"])>=37
    assert any(probe["name"]=="room_35" for probe in game["probes"])
    assert game["constructive_maze_design"]["challenge"]=="spicy"
    assert game["source"]=="strictly original generated game-world graph"
    assert "step_world" in project.files["src/main.c"]
    assert "dragon_probe_route_" in project.files["include/dragon_route_world.h"]
    assert "add_executable" in project.files["CMakeLists.txt"]
    assert "maze completion" not in project.files["README.routes.md"] or (
        "complete" in project.files["README.routes.md"])


def test_maze_project_source_release_verifies_without_trusting_author_receipt():
    req=original_maze_request()
    project=_render(req,"pc_linux")
    payload,receipt=make_source_release(project,req)
    verified=verify_source_release(payload)
    assert verified["source_fingerprint"]==project.digest
    assert receipt.target=="pc_linux"
    with ZipFile(BytesIO(payload)) as archive:
        paths=[name for name in archive.namelist()
               if name.endswith("/dragon-original-route-proof.json")]
        assert len(paths)==1
        native=json.loads(archive.read(paths[0]))
        assert native["constructive_maze_verification"]["rooms"]==36
        assert native["constructive_maze_certificate"]["all_climates_backbone_verified"]==[
            "clear","rain","windy","storm","snow","high_tide",
        ]


@pytest.mark.skipif(not shutil.which("cc"),reason="requires an actual host C99 compiler")
def test_generated_desktop_maze_compiles_and_replays_each_real_chamber(tmp_path):
    project=_render(original_maze_request(),"pc_linux")
    for name,text in project.files.items():
        path=tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding="utf-8")
    executable=tmp_path/"dragon_route_game"
    compiler=subprocess.run(
        ["cc","-O2","-std=c99","-Wall","-Wextra","-pedantic",
         "-Iinclude","src/main.c","-o",str(executable)],
        cwd=tmp_path,capture_output=True,text=True,timeout=50,
    )
    assert compiler.returncode==0,compiler.stderr
    run=subprocess.run(
        [str(executable),"--selftest"],cwd=tmp_path,
        capture_output=True,text=True,timeout=50,
    )
    assert run.returncode==0,(run.stdout,run.stderr)
    witnesses=json.loads(project.files["dragon-original-route-proof.json"])["probes"]
    assert run.stdout.count("DRAGON_ORIGINAL_ROUTE_PASS name=")==len(witnesses)
    assert "DRAGON_ORIGINAL_ROUTE_PASS name=maze_spine" in run.stdout
    assert "DRAGON_ORIGINAL_ROUTE_PASS name=room_35" in run.stdout


def test_original_maze_different_seeds_have_different_source_identities():
    first=_render(original_maze_request(seed=1),"pc_linux")
    again=_render(original_maze_request(seed=1),"pc_linux")
    second=_render(original_maze_request(seed=2),"pc_linux")
    assert first.digest==again.digest
    assert first.digest!=second.digest
