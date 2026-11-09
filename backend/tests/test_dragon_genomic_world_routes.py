"""Owner-only API can request astronomical indices as strings, not JS floats."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_world_genome import (
    GENOME_VARIATIONS,GENOMIC_WORLD_COUNT,AXIS_NAMES,
)
from skeleton.ai.webcrawler.dragon_genomic_paths import (
    PROGRAM_COUNT,GLOBAL_CHOICE_PATH_COUNT,
)


def editor():
    return route._native_source_editor({
        "email":"world-genome-editor@example.test",
        "role":"editor","tenant_id":"original-genomic-worlds",
    })


def test_capabilities_expose_exact_large_decimal_strings_not_float_corrupted_count():
    out=route.native_genomic_world_capabilities(owner=editor())
    assert out["ok"]
    g=out["genomic_world_space"]
    assert g["controlled_simulation_axes"]==24
    assert g["genomes_per_original_base_design"]==str(2**96)
    assert g["reversibly_addressable_world_configurations"]==str(
        GENOMIC_WORLD_COUNT)
    assert len(g["axes"])==24
    assert out["real_choice_path_space"]["globally_addressable_choice_paths"]==str(
        GLOBAL_CHOICE_PATH_COUNT)
    assert g["completed_or_legally_cleared_games"]==0


@pytest.mark.parametrize("address",[
    "0","1",str(2**96-1),str(2**96),str(GENOMIC_WORLD_COUNT-1),
])
def test_creator_can_materialize_actual_world_cells_at_huge_unrounded_address(address):
    out=route.native_genomic_world_inspect(
        route.NativeGenomicWorldRequest(index=address),owner=editor())
    assert out["ok"]
    assert out["source_address"]["decimal_index"]==address
    assert out["materialized_cells"]==25
    game=out["actual_game_state"]
    assert game["schema"]=="skeleton.ai.dragon.genomic_world_play.v1"
    assert game["player"]["base"]["turn"]==0
    assert game["actions"]
    assert len(game["physical_controls"])==24
    assert game["local_terrain"][12]["terrain_affects_gameplay"]
    assert game["lifecycle"]==out["source_address"]["lifecycle"]


def test_each_gameplay_axis_is_editable_and_changes_real_gameplay_not_only_id():
    maker=editor()
    update=route.native_genomic_world_edit(
        route.NativeGenomicWorldEditRequest(index="0",changes={
            "watershed":15,"traversal_drag":15,"sky_islands":15,
        }),owner=maker)
    assert update["ok"]
    assert update["reversible_decimal_address"]!= "0"
    assert update["updated_source"]["levels"][2]==15
    assert update["updated_source"]["levels"][17]==15
    assert update["updated_source"]["levels"][4]==15
    assert len(update["modified_actual_simulation_controls"])==3
    before=route.native_genomic_world_inspect(
        route.NativeGenomicWorldRequest(index="0"),owner=maker)
    after=route.native_genomic_world_inspect(
        route.NativeGenomicWorldRequest(
            index=update["reversible_decimal_address"]),owner=maker)
    baseline=before["actual_game_state"]["local_terrain"][12][
        "genomic_environment"]
    evolved=after["actual_game_state"]["local_terrain"][12][
        "genomic_environment"]
    assert baseline["travel_friction"]==1
    assert evolved["travel_friction"]==16
    assert evolved["water_depth"]>=30
    assert evolved["sky_density"]>=15


def test_live_genomic_world_can_replay_actions_and_deny_unaffordable_travel():
    maker=editor()
    addr=route.native_genomic_world_edit(
        route.NativeGenomicWorldEditRequest(index="0",changes={
            "watershed":15,"sky_islands":15,"cavern_density":15,
        }),owner=maker)["reversible_decimal_address"]
    initial=route.native_genomic_world_inspect(
        route.NativeGenomicWorldRequest(index=addr),owner=maker)
    choices={item["name"]:item for item in initial["actual_game_state"]["actions"]}
    assert choices["ride_river"]["available"]
    assert choices["cave_shortcut"]["available"]
    assert not choices["glide_sky"]["available"]
    with pytest.raises(HTTPException) as denied:
        route.native_genomic_world_play(
            route.NativeGenomicWorldPlayRequest(
                index=addr,actions=["glide_sky"],
            ),owner=maker)
    assert denied.value.status_code==422
    gameplay=route.native_genomic_world_play(
        route.NativeGenomicWorldPlayRequest(
            index=addr,actions=["scan_skies","glide_sky","study_river",
                               "forage_food","ride_river"],
        ),owner=maker)
    assert gameplay["ok"]
    assert gameplay["replayed_actions"][-1]=="ride_river"
    state=gameplay["actual_game_state"]["player"]
    assert state["base"]["turn"]==5
    assert state["base"]["x"]>0
    assert state["hydration"]>0
    assert len(gameplay["final_history_digest"])==64
    again=route.native_genomic_world_play(
        route.NativeGenomicWorldPlayRequest(
            index=addr,actions=["scan_skies","glide_sky","study_river",
                               "forage_food","ride_river"],
        ),owner=maker)
    assert again["final_history_digest"]==gameplay["final_history_digest"]


@pytest.mark.parametrize("index",[
    "0",str(PROGRAM_COUNT-1),
    str(GLOBAL_CHOICE_PATH_COUNT//2),
    str(GLOBAL_CHOICE_PATH_COUNT-1),
])
def test_large_address_routes_execute_sixteen_actual_game_actions_and_verify(index):
    result=route.native_genomic_world_path(
        route.NativeGenomicPathRequest(path_index=index),owner=editor())
    assert result["ok"]
    assert result["independent_verification"]["verified"]
    assert result["independent_verification"]["actual_actions"]==16
    assert result["source_path"]["decimal_path_index"]==index
    assert len(result["source_path"]["actions"])==16
    assert result["source_path"]["actually_played"]
    assert not result["source_path"]["finished_game_release_approved"]


def test_route_portfolio_samples_actual_play_without_fabricating_billions_of_results():
    results=route.native_genomic_world_sample_paths(
        route.NativeGenomicPathSampleRequest(index="0",limit=3),owner=editor())
    assert results["ok"]
    assert results["sampled_count"]==3
    assert results["distinct_actual_action_histories"]==3
    assert len(results["routes"])==3
    assert "only these sampled paths" in results["claim"]


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/genome/inspect",
    "/api/dragon-academy/native/production/worlds/genome/play",
    "/api/dragon-academy/native/production/worlds/genome/edit",
    "/api/dragon-academy/native/production/worlds/genome/path",
    "/api/dragon-academy/native/production/worlds/genome/sample-paths",
])
def test_astronomical_world_materialization_is_authenticated_creator_only(endpoint):
    row=next(r for r in route.router.routes if r.path==endpoint)
    assert any(dep.call is route._native_source_editor
               for dep in row.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"spectator@example.test","role":"viewer",
            "tenant_id":"original-genomic-worlds",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("bad",[
    {"index":"00"},{"index":"1e42"},{"index":"-1"},
    {"index":"100000000000000000000000000000000000000000000000000000000000000000000000000000000000"},
    {"index":True},{"index":1000},
    {"index":"0","untrusted_rom":"asset"},
])
def test_quintillion_world_index_has_only_exact_canonical_decimal_string_input(bad):
    with pytest.raises(ValidationError):
        route.NativeGenomicWorldRequest(**bad)


def test_large_value_with_valid_string_shape_but_out_of_range_has_422():
    with pytest.raises(HTTPException) as denied:
        route.native_genomic_world_inspect(route.NativeGenomicWorldRequest(
            index=str(GENOMIC_WORLD_COUNT)),owner=editor())
    assert denied.value.status_code==422


@pytest.mark.parametrize("wrong",[
    {"changes":{"fictional_no_gameplay":7}},
    {"changes":{"watershed":True}},
    {"changes":{"watershed":16}},
    {"changes":{"watershed":-1}},
])
def test_creators_cannot_inject_nonimplemented_physics_axes_or_overflow(wrong):
    if isinstance(wrong["changes"].get("watershed"),int) and (
        wrong["changes"]["watershed"] not in range(16)
    ):
        # Strict int preserves these for typed domain reject at gameplay edge.
        with pytest.raises(HTTPException):
            route.native_genomic_world_edit(
                route.NativeGenomicWorldEditRequest(index="0",**wrong),
                owner=editor())
    elif "fictional_no_gameplay" in wrong["changes"]:
        with pytest.raises(HTTPException):
            route.native_genomic_world_edit(
                route.NativeGenomicWorldEditRequest(index="0",**wrong),
                owner=editor())
    else:
        with pytest.raises(ValidationError):
            route.NativeGenomicWorldEditRequest(index="0",**wrong)
