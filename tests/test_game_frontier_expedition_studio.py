"""Forge Studio authoring to real replayable 3D expedition and original assets."""
from dataclasses import replace

import pytest

from skeleton.forge.game_frontier_studio import (
    MapLayer, StudioError, StudioPlacement, StudioPrefab, StudioProject,
    author_studio_expedition, compile_studio_expedition,
    compile_studio_project,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionEpisode, ExpeditionAction, Traveler, find_route, verify_route,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,
)


def project(*, projection=ProjectionMode.FULL_3D, placements=True):
    prefabs=(
        StudioPrefab("explorer","character","early_3d","a"*64),
        StudioPrefab("island_shrine","building","early_3d","b"*64),
        StudioPrefab("ancient_gate","portal","early_3d","c"*64),
        StudioPrefab("sky_ore","prop","early_3d","d"*64,interaction_type="pickup"),
    )
    spots=(
        StudioPlacement("explorer",0,0,0),
        StudioPlacement("island_shrine",26,9,12),
        StudioPlacement("ancient_gate",45,7,18),
        StudioPlacement("sky_ore",14,7,15),
    ) if placements else ()
    layer=MapLayer("primary",6,6,("stone","grass"),(1,)*36,elevation_m=0)
    return StudioProject(
        "skyforge", "early_3d", projection,
        WorldFamily.ORIGINAL,(layer,),prefabs,spots,
    )


def profile():
    return ArchipelagoProfile(seed=99,islands=8,caverns=2)


def test_real_studio_placements_become_traversable_3d_landmarks():
    p=project()
    world=author_studio_expedition(p,profile())
    assert world.source_digest==compile_studio_project(p)["content_sha256"]
    assert len(world.waypoints)>=4+profile().islands
    for i, placement in enumerate(p.placements):
        node=world.by_id[f"asset_{i:04d}"]
        assert (node.x_m,node.y_m,node.altitude_m)==(
            placement.x,placement.y,placement.z
        )
        access=world.by_edge[f"studio_access_{i:04d}"]
        assert access.target==node.waypoint_id
        assert world.by_edge[access.edge_id+".reverse"].target==access.source
    assert world.by_id["asset_0001"].safe_rest
    assert world.by_id["asset_0003"].collectible=="artifact_0003"
    assert world.by_id["asset_0003"].quest_flag=="visited_0003"


def test_compiler_emits_source_bound_complete_engine_data_and_playthrough():
    p=project()
    result=compile_studio_expedition(p,profile(),playtest_routes=4)
    assert result["schema"]=="skeleton.forge.frontier_studio_expedition.v1"
    assert result["project_id"]=="skyforge"
    assert result["playtest"]["all_ended_at_destination"]
    assert result["playtest"]["routes_executed"]>=2
    assert result["world_digest"]==result["engine_candidate"]["world_digest"]
    assert result["studio_source_digest"]==compile_studio_project(p)["content_sha256"]
    assert len(result["asset_bindings"])==4
    assert result["asset_bindings"][1]["asset_digest"]=="b"*64
    assert result["engine_candidate"]["asset_path"]=="game/frontier/expedition.json"
    assert result["native_playtest_completed"] is False
    assert len(result["receipt_digest"])==64
    assert result==compile_studio_expedition(p,profile(),playtest_routes=4)


def test_authored_side_mission_is_reversible_not_teleporting():
    world=author_studio_expedition(project(),profile())
    p=Traveler(
        permitted_modes=frozenset(("rope_bridge","walk","updraft")),
        flags=frozenset(("glider",)),max_stamina=1000,
    )
    episode=ExpeditionEpisode(world,p)
    inbound=world.by_edge["studio_access_0000"]
    # Discover the original placement via its actual authored connecting edge.
    # The nearest realm anchor need not be the harbor, so route first.
    if inbound.source!=episode.position:
        route=find_route(world,p,inbound.source)
        for edge in route.edge_ids:
            episode.step(ExpeditionAction("travel",edge))
    step=episode.step(ExpeditionAction("travel",inbound.edge_id))
    assert step["state"]["position"]=="asset_0000"
    exit=episode.step(ExpeditionAction("travel",inbound.edge_id+".reverse"))
    assert exit["state"]["position"]==inbound.source


def test_source_asset_edit_invalidates_replayed_expedition_world():
    p=project()
    original=author_studio_expedition(p,profile())
    changed=replace(p,prefabs=(
        p.prefabs[0],replace(p.prefabs[1],asset_digest="e"*64),
        p.prefabs[2],p.prefabs[3],
    ))
    revised=author_studio_expedition(changed,profile())
    assert revised.source_digest!=original.source_digest
    assert revised.digest!=original.digest
    traveler=Traveler(permitted_modes=frozenset(("walk","rope_bridge")))
    saved=ExpeditionEpisode(original,traveler).snapshot()
    with pytest.raises(ValueError,match="different world"):
        ExpeditionEpisode.restore(revised,traveler,saved)


def test_top_down_project_requires_valid_3d_projection():
    with pytest.raises(StudioError,match="requires 3D"):
        author_studio_expedition(project(projection=ProjectionMode.TOP_DOWN),profile())


def test_no_placements_still_produces_playable_original_world():
    result=compile_studio_expedition(
        project(placements=False),profile(),playtest_routes=3,
    )
    assert result["asset_bindings"]==[]
    assert result["playtest"]["routes_executed"]>=2


@pytest.mark.parametrize("bad",(0,17,True,"4"))
def test_studio_route_budget_strictly_finite(bad):
    with pytest.raises(StudioError,match="route budget"):
        compile_studio_expedition(project(),profile(),playtest_routes=bad)


def test_studio_rejects_placement_outside_game_coordinate_budget():
    p=project()
    moved=replace(p,placements=(StudioPlacement("explorer",3e6,0,0),))
    with pytest.raises(StudioError,match="cannot enter"):
        author_studio_expedition(moved,profile())


def test_engine_candidate_does_not_claim_godot_native_execution():
    result=compile_studio_expedition(project(),profile())
    assert result["engine_candidate"]["requires_native_loader"]
    assert not result["native_playtest_completed"]
    assert result["playtest"]["requires_native_godot_playtest"]
