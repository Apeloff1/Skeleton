"""Actual desktop C99 original maze game and editor/API integration."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile
import json,shutil,subprocess
import pytest

from skeleton.ai.webcrawler.dragon_route_maze import (
    MazeRequest,build_maze,verify_maze,WEATHERS,
)
from skeleton.ai.webcrawler.dragon_route_native_game import emit_route_game
from skeleton.ai.webcrawler.dragon_route_world import replay


@pytest.mark.parametrize("width,height,weather",[
    (4,4,"clear"),(5,4,"rain"),(6,6,"windy"),(8,6,"storm"),
])
def test_native_game_includes_actual_source_verified_route_for_every_room(
    width,height,weather,
):
    maze=build_maze(MazeRequest(width=width,height=height,weather=weather,
        seed=1977,scenic_density=90,detour_density=80))
    files=emit_route_game(maze.world,maze.traveller,
                          authorized=True,maze_creation=maze)
    manifest=json.loads(files["dragon-original-route-proof.json"])
    certificate=manifest["constructive_maze_certificate"]
    assert manifest["constructive_maze_verification"]["status"]=="constructively_complete"
    assert len(certificate["location_recovery_routes"])==width*height
    witnesses=manifest["probes"]
    assert len(witnesses)>=width*height+1
    assert {f"room_{i}" for i in range(width*height)}<={
        witness["name"] for witness in witnesses}
    for probe in witnesses:
        if probe["name"].startswith("room_"):
            room=int(probe["name"].removeprefix("room_"))
            assert probe["checkpoint_place"]==room
            assert probe["checkpoint_step"]>=0
            if probe["checkpoint_step"]==0:
                assert maze.world.places[room].id==maze.world.start
            else:
                visited_edge=probe["route"][probe["checkpoint_step"]-1]
                traversed=next(x for x in maze.world.connections
                               if x.id==visited_edge)
                assert traversed.destination==maze.world.places[room].id
        else:
            assert probe["checkpoint_step"]==-1
    assert "maze_spine" in {w["name"] for w in witnesses}
    assert any(w["name"].startswith("scenic_") for w in witnesses)
    assert any(w["name"].startswith("doubleback_") for w in witnesses)
    assert any(w["name"].startswith("secret_") for w in witnesses)
    for witness in witnesses:
        played=replay(maze.world,tuple(witness["route"]),maze.traveller,
                      objective="native_witness")
        assert played.success
        assert played.digest==witness["digest"]
        assert played.elapsed_minutes==witness["elapsed"]
    assert "run_probes" in files["src/main.c"]
    assert "DRAGON_ORIGINAL_WORLD_PASS" in files["src/main.c"]
    assert "dragon_connections" in files["include/dragon_route_world.h"]


@pytest.mark.skipif(not shutil.which("cc"),reason="real native C99 compiler required")
@pytest.mark.parametrize("width,height",[(4,4),(6,6),(8,6)])
def test_actual_c99_maze_source_compiles_and_replays_every_room_and_doubleback(
    tmp_path,width,height,
):
    maze=build_maze(MazeRequest(
        width=width,height=height,seed=2026,
        scenic_density=85,detour_density=70,
    ))
    files=emit_route_game(maze.world,maze.traveller,authorized=True,
                          maze_creation=maze)
    for name,content in files.items():
        location=tmp_path/name
        location.parent.mkdir(parents=True,exist_ok=True)
        location.write_text(content,encoding="utf-8")
    executable=tmp_path/"dragon_route_game"
    built=subprocess.run(
        ["cc","-std=c99","-O2","-Wall","-Wextra","-Werror","-pedantic",
         "-Iinclude","src/main.c","-o",str(executable)],
        cwd=tmp_path,capture_output=True,text=True,timeout=50,
    )
    assert built.returncode==0,built.stderr
    played=subprocess.run(
        [str(executable),"--selftest"],cwd=tmp_path,
        capture_output=True,text=True,timeout=45,
    )
    assert played.returncode==0,(played.stdout,played.stderr)
    entries=json.loads(files["dragon-original-route-proof.json"])["probes"]
    assert played.stdout.count("DRAGON_ORIGINAL_ROUTE_PASS name=")==len(entries)
    assert played.stdout.strip().endswith(
        f"DRAGON_ORIGINAL_WORLD_PASS probes={len(entries)} "
        f"places={len(maze.world.places)} routes={len(maze.world.connections)}"
    )


def test_cannot_export_altered_maze_as_if_it_passed_constructive_certification():
    maze=build_maze(MazeRequest(seed=45,width=5,height=4))
    broken=replace(maze.world,connections=maze.world.connections[:-1])
    with pytest.raises(ValueError):
        emit_route_game(broken,maze.traveller,authorized=True,
                        maze_creation=replace(maze,world=broken))
    with pytest.raises(PermissionError):
        emit_route_game(maze.world,maze.traveller,authorized=False,
                        maze_creation=maze)


def test_measured_maze_spine_is_not_silently_replaced_by_inferred_shortest_path():
    maize=build_maze(MazeRequest(seed=741,width=6,height=6,challenge="spicy"))
    manifest=json.loads(emit_route_game(
        maize.world,maize.traveller,authorized=True,maze_creation=maize,
    )["dragon-original-route-proof.json"])
    assert manifest["constructive_maze_certificate"]["backbone_moves"]>=15
    assert manifest["constructive_maze_certificate"]["main_journey_digest"]==(
        maize.certificate.main_journey_digest)
    assert manifest["constructive_maze_verification"]["rooms"]==36
    assert not manifest["originality_screen"]["finished_game_release_approved"]
    assert "human_originality_and_similarity_review" in (
        manifest["originality_screen"]["uncompleted_release_checks"])
