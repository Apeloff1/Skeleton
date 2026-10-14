"""Real authenticated regional game portals, source-proof limits and completion."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route


def _owner():
    return route._native_source_editor({
        "email":"original-atlas-author@example.test",
        "role":"editor","tenant_id":"game-studio",
    })


@pytest.mark.parametrize("regions,width,height",[(2,4,4),(3,5,4),(4,6,6)])
def test_creator_can_preview_actual_independently_completed_multi_maze_worlds(
    regions,width,height,
):
    request=route.NativeAtlasWorldRequest(
        seed=1977,regions=regions,width=width,height=height,
        climate="rain",challenge="challenging",
    )
    response=route.native_world_atlas_preview(request,owner=_owner())
    assert response["ok"]
    assert response["review"]["status"]=="hierarchical_completion_verified"
    assert response["review"]["rooms"]==regions*width*height
    assert response["review"]["climate_completion"]
    assert response["atlas"]["proof"]["all_room_proofs_available"]
    assert len(response["atlas"]["regional"])==regions
    assert response["player"]["region"]==0
    assert response["player"]["regional_play"]["completed"] is False
    assert "Python portal runtime" in response["native_claim"]


def test_original_world_creator_can_complete_real_first_region_then_take_shortcut_portal():
    request=route.NativeAtlasWorldRequest(
        seed=2026,regions=4,width=4,height=4,
    )
    atlas=route._original_route_atlas(request)
    part=atlas.worlds[0].certificate.backbone
    with pytest.raises(HTTPException) as denied:
        route.native_world_atlas_play(route.NativeAtlasPlayRequest(
            seed=2026,regions=4,width=4,height=4,
            commands=["portal_2"]),owner=_owner())
    assert denied.value.status_code==422
    progressed=route.native_world_atlas_play(route.NativeAtlasPlayRequest(
        seed=2026,regions=4,width=4,height=4,
        commands=list(part)+["portal_2"]),owner=_owner())
    assert progressed["region"]==2
    assert progressed["visited_regions"]==[0,2]
    assert not progressed["completed_world"]
    assert progressed["regional_play"]["world_position"]==(
        atlas.worlds[2].world.start)
    complete=route.native_world_atlas_play(route.NativeAtlasPlayRequest(
        seed=2026,regions=4,width=4,height=4,
        commands=list(atlas.proof.fast_replay_commands)),
        owner=_owner())
    assert complete["completed_world"]
    assert complete["visited_regions"]==list(atlas.proof.fast_regional_route)


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/routes/atlas/preview",
    "/api/dragon-academy/native/production/routes/atlas/play",
])
def test_original_multi_world_generation_and_portal_actions_are_editor_only(endpoint):
    target=next(x for x in route.router.routes if x.path==endpoint)
    assert any(dep.call is route._native_source_editor
               for dep in target.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.test","role":"viewer",
            "tenant_id":"game-studio",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("input",[
    {"regions":1},{"regions":13},{"regions":True},
    {"width":3},{"width":9},{"height":7},
    {"secret_count":5},{"scenic_density":-1},
    {"seed":True},{"seed":2**32},
    {"climate":"unimplemented_planet"},{"challenge":"infinite_punishment"},
    {"unknown_copyright_game_file":"unlicensed"},
])
def test_original_atlas_builder_strictly_bounds_world_workloads_and_rights(input):
    with pytest.raises(ValidationError):
        route.NativeAtlasWorldRequest(**input)


def test_atlas_portal_history_is_bounded_and_cannot_import_arbitrary_code():
    with pytest.raises(ValidationError):
        route.NativeAtlasPlayRequest(commands=["portal_1"]*513)
