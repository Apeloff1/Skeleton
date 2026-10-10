"""Original constructively solvable maze creator: secure API and real native code."""
from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import json
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from routes import dragon_academy as route


def _owner():
    return route._native_source_editor({
        "email":"original-maze-author@example.test",
        "role":"editor","tenant_id":"maze-studio",
    })


@pytest.mark.parametrize("dimensions",[(4,4),(5,5),(6,6),(8,6)])
def test_maze_editor_certificate_independently_covers_every_real_world_room(dimensions):
    width,height=dimensions
    payload=route.NativeMazeWorldRequest(
        width=width,height=height,seed=1977,
        scenic_density=100,detour_density=85,
        secret_count=2,weather="rain",
    )
    preview=route.native_world_maze_preview(payload,owner=_owner())
    assert preview["ok"]
    assert preview["source_only"]
    assert preview["completion"]["status"]=="constructively_complete"
    assert preview["completion"]["rooms"]==width*height
    assert preview["completion"]["all_climates"]==[
        "clear","rain","windy","storm","snow","high_tide",
    ]
    cert=preview["certificate"]
    assert len(cert["location_recovery_routes"])==width*height
    assert len(cert["location_recovery_verified"])==width*height
    assert cert["secret_witnesses"] and cert["doubleback_witnesses"]
    assert len(cert["certificate_digest"])==64
    assert preview["player"]["world_position"]==cert["start"]
    assert preview["player"]["completed"] is False


def test_actual_creator_can_do_doubleback_and_unlock_secret_without_fabricated_token():
    from skeleton.ai.webcrawler.dragon_route_maze import MazeRequest,build_maze
    design=MazeRequest(seed=2026,width=6,height=6)
    created=build_maze(design)
    path=created.certificate.secret_witnesses[0]
    first=route.NativeMazePlayRequest(
        seed=design.seed,width=design.width,height=design.height,
        moves=list(path[:3]),
    )
    review=route.native_world_maze_play(first,owner=_owner())
    assert review["ok"] and len(review["played_edges"])==3
    complete=route.NativeMazePlayRequest(
        seed=design.seed,width=design.width,height=design.height,
        moves=list(path),
    )
    finished=route.native_world_maze_play(complete,owner=_owner())
    assert finished["completed"] and finished["world_position"]==created.world.goal
    assert any(token.startswith("maze_clue_") for token in finished["known_tokens"])
    # Cannot jump through the secret shortcut directly from the start,
    # even though the server can prove this path exists for a truthful run.
    illegal=route.NativeMazePlayRequest(
        seed=design.seed,width=design.width,height=design.height,
        moves=[next(edge.id for edge in created.world.connections
                    if edge.secret_token)],
    )
    with pytest.raises(HTTPException) as denied:
        route.native_world_maze_play(illegal,owner=_owner())
    assert denied.value.status_code==422


def test_actual_native_game_maze_archive_has_certified_room_probes_and_no_binary():
    body=route.NativeMazeSourceRequest(
        width=5,height=4,seed=7,
        original_work_attested=True,approved=True,
    )
    export=route.native_world_maze_source_bundle(body,owner=_owner())
    assert export.media_type=="application/zip"
    assert export.headers["x-dragon-claim"]=="original-source-only-native-C99-not-compiled"
    assert export.headers["x-content-sha256"]==sha256(export.body).hexdigest()
    with ZipFile(BytesIO(export.body)) as package:
        assert set(package.namelist())=={
            "src/main.c","include/dragon_route_world.h",
            "dragon-original-route-proof.json","Makefile","CMakeLists.txt",
            "README.md",
        }
        contents=json.loads(package.read("dragon-original-route-proof.json"))
        evidence=contents["constructive_maze_certificate"]
        assert evidence["location_recovery_count"]==20
        assert contents["constructive_maze_verification"]["status"]=="constructively_complete"
        assert len(contents["probes"])>=21
        assert not contents["originality_screen"]["finished_game_release_approved"]
        assert b"int main" in package.read("src/main.c")
        assert package.getinfo("src/main.c").date_time==(1980,1,1,0,0,0,)


def test_original_maze_export_requires_separate_creation_rights_and_approval():
    with pytest.raises(HTTPException) as exc:
        route.native_world_maze_source_bundle(
            route.NativeMazeSourceRequest(approved=True),
            owner=_owner(),
        )
    assert exc.value.status_code==403


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/routes/maze/preview",
    "/api/dragon-academy/native/production/routes/maze/play",
    "/api/dragon-academy/native/production/routes/maze/source-bundle",
])
def test_original_maze_solver_generation_and_export_are_not_available_to_viewers(endpoint):
    selected=next(item for item in route.router.routes if item.path==endpoint)
    assert any(dep.call is route._native_source_editor
               for dep in selected.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.test","role":"viewer",
            "tenant_id":"maze-studio",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("invalid",[
    {"width":3},{"width":9},{"height":3},{"height":7},
    {"seed":True},{"seed":-1},{"seed":2**32},
    {"scenic_density":101},{"detour_density":-1},{"secret_count":5},
    {"weather":"fictional_neverending_storm"},{"challenge":"punishment_only"},
    {"attempt_to_import_proprietary_rom":"unauthorized"},
])
def test_original_maze_request_fails_closed_on_invalid_world_controls(invalid):
    with pytest.raises(ValidationError):
        route.NativeMazeWorldRequest(**invalid)


def test_original_maze_request_rejects_more_than_80_playable_decisions():
    with pytest.raises(ValidationError):
        route.NativeMazePlayRequest(moves=["spine_0_0_0_1"]*81)
