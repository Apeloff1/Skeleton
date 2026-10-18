"""Authenticated large Codex world creation, delayed routes, original story, C99."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_world_codex import (
    CODEX_WORLD_ADDRESSES,EXTENDED_CODEX_WORLD_ADDRESSES,DOMAINS,
)


def owner():
    return route._native_source_editor({
        "email":"author@example.test","role":"editor",
        "tenant_id":"original-codex-works",
    })


def test_exact_huge_world_capacity_never_counts_unbuilt_games():
    data=route.native_world_codex_capabilities(owner=owner())
    assert data["ok"]
    assert data["codex"]["axes"]==192
    assert data["codex"]["domains"]==24
    assert data["codex"]["levels_per_axis"]==256
    assert data["codex"]["total_exact_reversible_original_world_addresses"]==(
        str(EXTENDED_CODEX_WORLD_ADDRESSES))
    assert data["codex"]["enumerated_games"]==0
    assert data["codex"]["independently_reviewed_unique_games"]==0


@pytest.mark.parametrize("index",[
    "0","1",str(2**1024-1),str(2**1024),
    str(CODEX_WORLD_ADDRESSES-1),
])
def test_creator_can_generate_one_real_original_128_axis_world_at_huge_address(index):
    result=route.native_world_codex_inspect(
        route.NativeCodexWorldRequest(index=index),owner=owner())
    assert result["ok"]
    assert result["design"]["decimal_index"]==index
    assert len(result["design"]["values"])==128
    assert result["game"]["current_turn"]==0
    assert len(result["game"]["available_actions"])==146
    assert len(result["game"]["terrain"]["codex_terrain"])==16
    assert len(result["game"]["axes_level_map"])==128


def test_original_axis_edit_changes_real_world_weather_and_movement_conditions():
    edited=route.native_world_codex_edit(
        route.NativeCodexWorldEditRequest(index="0",changes={
            "storm_fronts":255,"elevation_tectonics":255,
            "time_window_strictness":200,
        }),owner=owner())
    assert edited["ok"]
    assert len(edited["changed_axes"])==3
    assert edited["new_decimal_index"]!="0"
    before=route.native_world_codex_inspect(
        route.NativeCodexWorldRequest(index="0"),owner=owner())
    after=route.native_world_codex_inspect(
        route.NativeCodexWorldRequest(index=edited["new_decimal_index"]),
        owner=owner())
    assert (before["game"]["terrain"]["codex_terrain"]["climate"]!=
            after["game"]["terrain"]["codex_terrain"]["climate"])
    assert before["game"]["gates"][0]["earliest_turn"]!=(
        after["game"]["gates"][0]["earliest_turn"])


def test_live_world_gate_denies_skip_then_allows_replayed_unlock():
    modified=route.native_world_codex_edit(
        route.NativeCodexWorldEditRequest(index="0",changes={
            "elevation_tectonics":255,"plate_migration":255,
        }),owner=owner())["new_decimal_index"]
    body=route.NativeCodexWorldRequest(index=modified)
    first=route.native_world_codex_inspect(body,owner=owner())
    assert first["game"]["gates"][0]["reason"]=="mastery_locked"
    with pytest.raises(HTTPException) as denied:
        route.native_world_codex_play(route.NativeCodexWorldPlayRequest(
            index=modified,actions=["traverse_cavern_depths"],
        ),owner=owner())
    assert denied.value.status_code==422
    proved=route.native_world_codex_unlock_witness(
        route.NativeCodexWorldGatewayRequest(index=modified,domain="geology"),
        owner=owner())
    assert proved["ok"]
    assert proved["completed_non_mandatory_passage"]
    assert proved["steps"]>=8
    final=route.native_world_codex_play(
        route.NativeCodexWorldPlayRequest(
            index=modified,actions=proved["actual_commands"],
        ),owner=owner())
    assert final["ok"]
    assert final["game"]["journeys"]==["traverse_cavern_depths"]
    assert final["game"]["current_position"]==[0,-2,-3]


def test_every_original_world_story_choice_is_temporally_and_socially_gated():
    started=route.native_world_codex_story(
        route.NativeCodexStoryRequest(index="0"),owner=owner())
    assert started["ok"]
    assert started["original_story_world"]["playable_after_story"]
    with pytest.raises(HTTPException):
        route.native_world_codex_story(
            route.NativeCodexStoryRequest(
                index="0",decisions=["choose_aftermath"],
            ),owner=owner())
    invested=route.native_world_codex_story(
        route.NativeCodexStoryRequest(
            index="0",decisions=["investigate","investigate",
            "support_commune","support_commune","complete_chapter",
            "choose_aftermath"],
        ),owner=owner())
    assert invested["ok"]
    assert invested["original_story_world"]["ended_a_story"]
    assert not invested["original_story_world"]["ended_the_world"]
    assert invested["original_story_world"]["playable_after_story"]
    assert invested["original_story_world"]["player"]["endings"]==[
        "communal_renewal"]


def test_original_hardware_content_is_recomputed_without_forging_rom():
    result=route.native_world_codex_compile_target(
        route.NativeCodexWorldPlatformRequest(
            index="0",target="game_boy",chunks=2,
        ),owner=owner())
    assert result["ok"]
    assert result["independent_verification"]["verified"]
    assert len(result["package"]["chunks"])==2
    assert result["package"]["native_binary"] is None
    assert not result["independent_verification"]["hardware_binary_verified"]
    assert result["package"]["projection"]["original_axis_count"]==128
    assert result["package"]["projection"]["active_axes"]<128


def test_c99_game_source_is_real_game_not_claimed_executable():
    response=route.native_world_codex_desktop_source(
        route.NativeCodexWorldRequest(index="0"),owner=owner())
    assert response["ok"]
    assert response["project"]["source_name"]=="dragon_codex_game.c"
    assert "#define AXES 128" in response["project"]["source"]
    assert "DRAGON_CODEX_SELFTEST_PASS" in response["project"]["source"]
    assert response["independent_source_verification"]["verified_source"]
    assert not response["project"]["actual_native_binary_produced"]


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/codex/inspect",
    "/api/dragon-academy/native/production/worlds/codex/edit",
    "/api/dragon-academy/native/production/worlds/codex/play",
    "/api/dragon-academy/native/production/worlds/codex/unlock-witness",
    "/api/dragon-academy/native/production/worlds/codex/compile-target",
    "/api/dragon-academy/native/production/worlds/codex/platforms",
    "/api/dragon-academy/native/production/worlds/codex/story",
    "/api/dragon-academy/native/production/worlds/codex/native-desktop-source",
])
def test_codex_world_creation_legal_profile_and_source_are_editor_only(endpoint):
    endpoint_record=next(x for x in route.router.routes if x.path==endpoint)
    assert any(x.call is route._native_source_editor
               for x in endpoint_record.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.test","role":"viewer",
            "tenant_id":"original-codex-works",
        })
    assert denied.value.status_code==403


@pytest.mark.parametrize("bad",[
    {"index":"0001"},{"index":"+5"},{"index":"1e350"},
    {"index":123},{"index":True},{"index":"9"*610},
    {"untrusted_copyright_source":"not permitted"},
])
def test_huge_world_addresses_reject_unsafe_or_inexact_web_json(bad):
    with pytest.raises(ValidationError):
        route.NativeCodexWorldRequest(**bad)


def test_legacy_world_address_is_not_reinterpreted_after_extension():
    from skeleton.ai.webcrawler.dragon_world_codex import (
        unrank,rank,edit,WorldCodex,SCHEMA,EXTENDED_SCHEMA,validate,
    )
    baseline=unrank("0")
    assert baseline.schema==SCHEMA
    assert baseline.decimal_index=="0"
    assert len(baseline.values)==128
    assert all(level==0 for level in baseline.extension_values)
    assert rank(baseline.parent_decimal_index,WorldCodex(baseline.values))=="0"
    assert edit("0",{"sky_islands":0})==baseline
    enhanced=edit("0",{"sky_islands":188,"cloud_oceans":131})
    assert enhanced.schema==EXTENDED_SCHEMA
    assert int(enhanced.decimal_index)>=CODEX_WORLD_ADDRESSES
    assert enhanced.codex_digest!=baseline.codex_digest
    _,levels=validate(enhanced)
    assert levels.level("sky_islands")==188
    assert levels.level("cloud_oceans")==131
    assert edit(enhanced.decimal_index,{"sky_islands":0,"cloud_oceans":0})==baseline


def test_versioned_sky_islands_stimulate_real_traversal_and_altitude():
    from skeleton.ai.webcrawler.dragon_world_codex import edit
    from skeleton.ai.webcrawler.dragon_world_codex_runtime import (
        start,report,step,gate_catalog,witness_to_gate,replay,
    )
    expanded=edit("0",{
        "sky_islands":188,"cloud_oceans":80,
        "wind_shear":120,"skybridge_density":0,
        "glider_lift":150,"floating_settlements":40,
    })
    opening=start(expanded)
    info=report(expanded,opening,detail=True)
    assert len(info["axes_level_map"])==192
    assert len(info["domain_progress"])==24
    assert len(info["available_actions"])==218
    assert info["axes_level_map"]["sky_islands"]==188
    assert "aerial_topology" in info["terrain"]
    aerial=next(x for x in info["gates"] if x["name"]=="cross_sky_islands")
    assert aerial["additional_prerequisites"]==[
        {"axis":"glider_lift","required":2,"current":0}]
    assert not aerial["available"]
    route=witness_to_gate(expanded,"aerial_realms")
    assert route.count("study_glider_lift")==2
    arrived=replay(expanded,route)
    assert arrived.altitude==1
    assert "cross_sky_islands" in arrived.opened_gates
    assert report(expanded,arrived)["terrain"]["aerial_topology"]["altitude_layer"]==1
    assert replay(expanded,route).history_digest==arrived.history_digest


def test_extended_codex_impact_endpoint_checks_both_art_and_world_paths():
    payload=route.NativeCodexWorldEditRequest(
        index="0",changes={
            "sky_islands":220,"thermal_updrafts":80,
            "cloud_oceans":110,"wind_shear":95,
            "skybridge_density":160,
        })
    result=route.native_world_codex_impact(payload,owner=owner())
    assert result["ok"]
    assert result["edited_index"]!="0"
    assert result["version"].endswith("v3")
    assert "aerial_realms" in result["affected_domains"]
    assert "atmosphere" in result["affected_domains"]
    assert result["terrain"]["changed"]
    assert result["terrain"]["aerial_before"] is None
    assert result["terrain"]["aerial_after"] is not None
    assert "cross_sky_islands" in result["traversal"]["additional_route_names"]
    assert result["tiles"]["before_count"]==12
    assert result["tiles"]["after_count"]==16
    assert "sky_island" in result["tiles"]["changed"]
    assert result["tiles"]["verified_roundtrip"]
    assert not result["tiles"]["hardware_binary_compiled"]


def test_extended_axes_refuse_non_canonical_and_forged_identities():
    from dataclasses import replace
    from skeleton.ai.webcrawler.dragon_world_codex import (
        edit,unrank,validate,read_index,EXTENDED_CODEX_WORLD_ADDRESSES,
    )
    enhanced=edit("0",{"sky_islands":200})
    with pytest.raises(ValueError):
        validate(replace(enhanced,extension_values=(0,)*64))
    with pytest.raises(ValueError):
        read_index(str(EXTENDED_CODEX_WORLD_ADDRESSES))
    with pytest.raises(ValueError):
        read_index("0"+enhanced.decimal_index)
    with pytest.raises(HTTPException) as unsupported:
        route.native_world_codex_edit(
            route.NativeCodexWorldEditRequest(changes={"sky_islands":True}),
            owner=owner(),
        )
    assert unsupported.value.status_code==422


def test_codecs_refuse_nonexistent_platform_or_axis_in_real_world_content():
    with pytest.raises(HTTPException) as unsupported:
        route.native_world_codex_compile_target(
            route.NativeCodexWorldPlatformRequest(
                target="unreleased_playstation_console",
            ),owner=owner())
    assert unsupported.value.status_code==422
    with pytest.raises(HTTPException) as unsupported:
        route.native_world_codex_edit(
            route.NativeCodexWorldEditRequest(
                changes={"copyright_game_feature":200},
            ),owner=owner())
    assert unsupported.value.status_code==422
